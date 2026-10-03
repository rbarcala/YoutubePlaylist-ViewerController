package com.fondosstream.controller;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.wifi.WifiManager;
import android.os.Bundle;
import android.os.Vibrator;
import android.text.format.Formatter;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
import android.Manifest;
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

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        prefs = getSharedPreferences("FondosStreamPrefs", Context.MODE_PRIVATE);

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
        String url = "file:///android_asset/connect.html";
        if (errorMsg != null && !errorMsg.isEmpty()) {
            try {
                url += "?error=" + java.net.URLEncoder.encode(errorMsg, "UTF-8");
            } catch (Exception ignored) {}
        }
        webView.loadUrl(url);
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
