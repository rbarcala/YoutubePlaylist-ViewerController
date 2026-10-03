package com.fondosstream.controller;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.view.View;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;

public class MainActivity extends Activity {

    private WebView webView;
    private SharedPreferences prefs;
    private static final String PREF_SERVER_IP = "server_ip";
    private static final String DEFAULT_PORT = "8000";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        prefs = getSharedPreferences("FondosStreamPrefs", Context.MODE_PRIVATE);

        webView = new WebView(this);
        setContentView(webView);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);

        webView.setWebChromeClient(new WebChromeClient());
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
                showIpDialog("Error al conectar: " + description);
            }
        });

        String savedIp = prefs.getString(PREF_SERVER_IP, "");
        if (savedIp.isEmpty()) {
            showIpDialog(null);
        } else {
            loadControllerUrl(savedIp);
        }
    }

    private void loadControllerUrl(String ipOrHost) {
        String url = ipOrHost;
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            if (!url.contains(":")) {
                url = "http://" + url + ":" + DEFAULT_PORT;
            } else {
                url = "http://" + url;
            }
        }
        if (!url.endsWith("/controller.html")) {
            if (url.endsWith("/")) {
                url += "controller.html";
            } else {
                url += "/controller.html";
            }
        }
        webView.loadUrl(url);
    }

    private void showIpDialog(String errorMessage) {
        AlertDialog.Builder builder = new AlertDialog.Builder(this);
        builder.setTitle(errorMessage != null ? errorMessage : "Conectar al Servidor");
        builder.setMessage("Ingresa la IP de tu PC en la red local (ej: 192.168.1.100 o localhost):");

        final EditText input = new EditText(this);
        input.setHint("192.168.1.100");
        input.setText(prefs.getString(PREF_SERVER_IP, ""));
        builder.setView(input);

        builder.setPositiveButton("Conectar", (dialog, which) -> {
            String ip = input.getText().toString().trim();
            if (!ip.isEmpty()) {
                prefs.edit().putString(PREF_SERVER_IP, ip).apply();
                loadControllerUrl(ip);
            }
        });

        builder.setCancelable(false);
        builder.show();
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
