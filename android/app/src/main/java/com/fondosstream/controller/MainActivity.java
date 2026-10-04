package com.fondosstream.controller;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
import android.net.wifi.WifiManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.Vibrator;
import android.text.format.Formatter;
import android.util.Log;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
import android.Manifest;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.Inet4Address;
import java.net.NetworkInterface;
import java.util.Collections;
import java.util.List;

public class MainActivity extends Activity {

    private WebView webView;
    private SharedPreferences prefs;
    private static final String PREF_SERVER_URL = "server_url";
    private static final String DEFAULT_PORT = "8000";
    private long lastBackPressTime = 0;

    // mDNS / Zeroconf / UDP Discovery
    private NsdManager nsdManager;
    private NsdManager.DiscoveryListener nsdDiscoveryListener;
    private WifiManager.MulticastLock multicastLock;
    private static final String TAG = "StreamDiscovery";
    private static final String SERVICE_TYPE = "_streamcontroller._tcp.";
    private boolean isAutoConnecting = false;
    private boolean isDiscovering = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        prefs = getSharedPreferences("FondosStreamPrefs", Context.MODE_PRIVATE);
        nsdManager = (NsdManager) getSystemService(Context.NSD_SERVICE);

        // Solicitar permiso de cámara para el escáner QR si no está concedido
        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.CAMERA}, 101);
        }

        webView = new WebView(this);
        setContentView(webView);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);

        // Puente JavaScript con Android para la pantalla de conexión
        webView.addJavascriptInterface(new WebAppInterface(), "AndroidBridge");

        // Permitir que el WebView use la cámara web en HTML5
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        request.grant(request.getResources());
                    }
                });
            }
        });

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                if (url != null && !url.startsWith("file://")) {
                    String lower = url.toLowerCase();
                    if (lower.startsWith("http://") || lower.startsWith("https://")) {
                        String currentServer = prefs.getString(PREF_SERVER_URL, "");
                        if (!currentServer.isEmpty() && !url.startsWith(currentServer)) {
                            try {
                                android.content.Intent intent = new android.content.Intent(android.content.Intent.ACTION_VIEW, android.net.Uri.parse(url));
                                startActivity(intent);
                                return true;
                            } catch (Exception ignored) {}
                        }
                    }
                }
                return false;
            }

            @Override
            public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
                if (failingUrl != null && !failingUrl.startsWith("file://")) {
                    Toast.makeText(MainActivity.this, "Error al conectar: " + description, Toast.LENGTH_SHORT).show();
                    loadConnectPage("No se pudo conectar al servidor: " + description);
                }
            }
        });

        String savedUrl = prefs.getString(PREF_SERVER_URL, "");
        if (savedUrl.isEmpty()) {
            loadConnectPage(null);
        } else {
            webView.loadUrl(savedUrl);
        }
    }

    private void loadConnectPage(String errorMsg) {
        isAutoConnecting = false;
        String url = "file:///android_asset/connect.html";
        if (errorMsg != null && !errorMsg.isEmpty()) {
            try {
                url += "?error=" + java.net.URLEncoder.encode(errorMsg, "UTF-8");
            } catch (Exception ignored) {}
        }
        webView.loadUrl(url);
        startAutoDiscovery();
    }

    // ─── AUTODETECCIÓN POR RED (mDNS / Zeroconf / UDP Beacon) ───

    private synchronized void startAutoDiscovery() {
        if (isDiscovering || isAutoConnecting) return;
        isDiscovering = true;

        acquireMulticastLock();
        startNsdDiscovery();
        startUdpDiscovery();
    }

    private void acquireMulticastLock() {
        try {
            WifiManager wm = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            if (wm != null && (multicastLock == null || !multicastLock.isHeld())) {
                multicastLock = wm.createMulticastLock("FondosStreamMdnsLock");
                multicastLock.setReferenceCounted(true);
                multicastLock.acquire();
            }
        } catch (Exception e) {
            Log.e(TAG, "Error acquiring multicast lock: " + e.getMessage());
        }
    }

    private synchronized void stopAutoDiscovery() {
        isDiscovering = false;
        if (nsdManager != null && nsdDiscoveryListener != null) {
            try {
                nsdManager.stopServiceDiscovery(nsdDiscoveryListener);
            } catch (Exception ignored) {}
            nsdDiscoveryListener = null;
        }
        if (multicastLock != null && multicastLock.isHeld()) {
            try {
                multicastLock.release();
            } catch (Exception ignored) {}
            multicastLock = null;
        }
    }

    private void startNsdDiscovery() {
        if (nsdManager == null) return;
        nsdDiscoveryListener = new NsdManager.DiscoveryListener() {
            @Override
            public void onDiscoveryStarted(String regType) {
                Log.d(TAG, "mDNS Discovery started: " + regType);
            }

            @Override
            public void onServiceFound(NsdServiceInfo service) {
                Log.d(TAG, "mDNS Service found: " + service);
                String type = service.getServiceType();
                String name = service.getServiceName();
                if ((type != null && type.contains("_streamcontroller")) || (name != null && name.contains("Stream Controller"))) {
                    try {
                        nsdManager.resolveService(service, new NsdManager.ResolveListener() {
                            @Override
                            public void onResolveFailed(NsdServiceInfo serviceInfo, int errorCode) {
                                Log.e(TAG, "Resolve failed: " + errorCode);
                            }

                            @Override
                            public void onServiceResolved(NsdServiceInfo serviceInfo) {
                                int port = serviceInfo.getPort();
                                InetAddress host = serviceInfo.getHost();
                                if (host != null) {
                                    String ip = host.getHostAddress();
                                    onServerDiscovered(ip, port, "mDNS / Zeroconf");
                                }
                            }
                        });
                    } catch (Exception e) {
                        Log.e(TAG, "Error resolving service: " + e.getMessage());
                    }
                }
            }

            @Override
            public void onServiceLost(NsdServiceInfo service) {
                Log.d(TAG, "Service lost: " + service);
            }

            @Override
            public void onDiscoveryStopped(String serviceType) {
                Log.d(TAG, "Discovery stopped");
            }

            @Override
            public void onStartDiscoveryFailed(String serviceType, int errorCode) {
                Log.e(TAG, "Start discovery failed: " + errorCode);
                stopAutoDiscovery();
            }

            @Override
            public void onStopDiscoveryFailed(String serviceType, int errorCode) {
                Log.e(TAG, "Stop discovery failed: " + errorCode);
            }
        };

        try {
            nsdManager.discoverServices(SERVICE_TYPE, NsdManager.PROTOCOL_DNS_SD, nsdDiscoveryListener);
        } catch (Exception e) {
            Log.e(TAG, "Error starting NSD: " + e.getMessage());
        }
    }

    private void startUdpDiscovery() {
        new Thread(new Runnable() {
            @Override
            public void run() {
                DatagramSocket socket = null;
                try {
                    socket = new DatagramSocket();
                    socket.setBroadcast(true);
                    socket.setSoTimeout(2000);
                    byte[] sendData = "STREAM_CONTROLLER_DISCOVER".getBytes();

                    // 1. Broadcast global
                    DatagramPacket packet = new DatagramPacket(sendData, sendData.length, InetAddress.getByName("255.255.255.255"), 8001);
                    socket.send(packet);

                    // 2. Broadcast de la subred local actual
                    String devIp = getDeviceWifiIp();
                    if (devIp != null && devIp.contains(".")) {
                        int lastDot = devIp.lastIndexOf('.');
                        String subnetBcast = devIp.substring(0, lastDot + 1) + "255";
                        DatagramPacket pSubnet = new DatagramPacket(sendData, sendData.length, InetAddress.getByName(subnetBcast), 8001);
                        socket.send(pSubnet);
                    }

                    byte[] recvBuf = new byte[1024];
                    DatagramPacket recvPacket = new DatagramPacket(recvBuf, recvBuf.length);
                    socket.receive(recvPacket);

                    String resp = new String(recvPacket.getData(), 0, recvPacket.getLength());
                    if (resp.startsWith("STREAM_CONTROLLER_SERVER:")) {
                        String[] parts = resp.split(":");
                        int port = 8000;
                        if (parts.length >= 2) {
                            try { port = Integer.parseInt(parts[1].trim()); } catch (Exception ignored) {}
                        }
                        String serverIp = recvPacket.getAddress().getHostAddress();
                        onServerDiscovered(serverIp, port, "Beacon UDP LAN");
                    }
                } catch (Exception ignored) {
                } finally {
                    if (socket != null) {
                        try { socket.close(); } catch (Exception ignored) {}
                    }
                }
            }
        }).start();
    }

    private synchronized void onServerDiscovered(String host, final int port, final String method) {
        if (host == null || host.equals("127.0.0.1") || host.equals("localhost") || host.startsWith("169.254")) {
            return; // Ignorar IPs inválidas para el teléfono
        }
        
        // Formatear IPv6 correctamente con corchetes
        if (host.contains(":") && !host.startsWith("[")) {
            host = "[" + host + "]";
        }
        
        if (isAutoConnecting) return;
        isAutoConnecting = true;

        final String finalHost = host;
        final String fullUrl = "http://" + finalHost + ":" + port + "/controller.html";
        Log.i(TAG, "✓ Servidor detectado vía " + method + ": " + fullUrl);

        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                // Notificar a connect.html si está en pantalla
                String js = "if(window.onAutoDiscovered) { window.onAutoDiscovered('" + finalHost + "', " + port + ", '" + fullUrl + "'); }";
                webView.evaluateJavascript(js, null);

                // Guardar la URL detectada
                prefs.edit().putString(PREF_SERVER_URL, fullUrl).apply();

                // Vibración de confirmación háptica
                try {
                    Vibrator v = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
                    if (v != null) v.vibrate(60);
                } catch (Exception ignored) {}

                // Cargar automáticamente en 750ms para permitir ver el feedback visual
                new Handler(Looper.getMainLooper()).postDelayed(new Runnable() {
                    @Override
                    public void run() {
                        stopAutoDiscovery();
                        webView.loadUrl(fullUrl);
                    }
                }, 750);
            }
        });
    }

    public String getDeviceWifiIp() {
        try {
            WifiManager wm = (WifiManager) getApplicationContext().getSystemService(WIFI_SERVICE);
            if (wm != null) {
                int ipInt = wm.getConnectionInfo().getIpAddress();
                if (ipInt != 0) {
                    return Formatter.formatIpAddress(ipInt);
                }
            }
        } catch (Exception ignored) {}

        try {
            List<NetworkInterface> interfaces = Collections.list(NetworkInterface.getNetworkInterfaces());
            for (NetworkInterface intf : interfaces) {
                List<InetAddress> addrs = Collections.list(intf.getInetAddresses());
                for (InetAddress addr : addrs) {
                    if (!addr.isLoopbackAddress() && addr instanceof Inet4Address) {
                        return addr.getHostAddress();
                    }
                }
            }
        } catch (Exception ignored) {}

        return "192.168.1.1";
    }

    public String resolveFullUrl(String input) {
        if (input == null) return "";
        String s = input.trim();
        if (s.isEmpty()) return "";

        // Si ya es una URL completa (ej: escaneada con QR)
        if (s.startsWith("http://") || s.startsWith("https://")) {
            if (!s.contains("/controller.html")) {
                if (s.endsWith("/")) s += "controller.html";
                else s += "/controller.html";
            }
            return s;
        }

        String port = DEFAULT_PORT;
        String host = s;

        if (host.contains(":")) {
            String[] parts = host.split(":", 2);
            host = parts[0];
            port = parts[1];
        }

        String devIp = getDeviceWifiIp();
        String[] hostParts = host.split("\\.");

        // Si solo escribió el número final (ej: "100" o "45")
        if (hostParts.length == 1) {
            String subnet = "192.168.1.";
            if (devIp != null && devIp.contains(".")) {
                int lastDot = devIp.lastIndexOf('.');
                subnet = devIp.substring(0, lastDot + 1);
            }
            host = subnet + hostParts[0];
        } else if (hostParts.length == 2) {
            // Escribió dos octetos (ej: "1.100")
            String prefix = "192.168.";
            if (devIp != null && devIp.contains(".")) {
                String[] devParts = devIp.split("\\.");
                if (devParts.length >= 2) {
                    prefix = devParts[0] + "." + devParts[1] + ".";
                }
            }
            host = prefix + host;
        }

        return "http://" + host + ":" + port + "/controller.html";
    }

    public class WebAppInterface {
        @JavascriptInterface
        public String getDeviceSubnet() {
            String devIp = getDeviceWifiIp();
            if (devIp != null && devIp.contains(".")) {
                int lastDot = devIp.lastIndexOf('.');
                return devIp.substring(0, lastDot + 1);
            }
            return "192.168.1.";
        }

        @JavascriptInterface
        public String getSavedUrl() {
            return prefs.getString(PREF_SERVER_URL, "");
        }

        @JavascriptInterface
        public void connect(final String rawInput) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    String fullUrl = resolveFullUrl(rawInput);
                    if (!fullUrl.isEmpty()) {
                        stopAutoDiscovery();
                        prefs.edit().putString(PREF_SERVER_URL, fullUrl).apply();
                        try {
                            Vibrator v = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
                            if (v != null) v.vibrate(50);
                        } catch (Exception ignored) {}
                        webView.loadUrl(fullUrl);
                    }
                }
            });
        }

        @JavascriptInterface
        public void retryDiscovery() {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    isAutoConnecting = false;
                    stopAutoDiscovery();
                    startAutoDiscovery();
                }
            });
        }

        @JavascriptInterface
        public void requestCamera() {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
                        requestPermissions(new String[]{Manifest.permission.CAMERA}, 101);
                    }
                }
            });
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        stopAutoDiscovery();
    }

    @Override
    public void onBackPressed() {
        String currentUrl = webView.getUrl();
        if (currentUrl != null && !currentUrl.startsWith("file://")) {
            long now = System.currentTimeMillis();
            if (now - lastBackPressTime < 2000) {
                // Doble toque hacia atrás: volver a la pantalla de conexión para cambiar de PC
                loadConnectPage(null);
                Toast.makeText(this, "Desconectado. Ingresa nueva IP o escanea QR", Toast.LENGTH_SHORT).show();
                return;
            } else {
                lastBackPressTime = now;
                if (webView.canGoBack()) {
                    webView.goBack();
                    return;
                }
                Toast.makeText(this, "Presiona ATRÁS de nuevo para cambiar de PC o desconectar", Toast.LENGTH_SHORT).show();
                return;
            }
        }

        super.onBackPressed();
    }
}
