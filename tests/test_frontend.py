"""
Pruebas de integridad del Frontend modular (HTML, CSS, JS).
Verifica que todos los archivos estáticos existan, enlacen correctamente sus módulos
y que los scripts JavaScript pasen la validación estricta de sintaxis.
"""

import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


class TestFrontendIntegrity(unittest.TestCase):

    def setUp(self):
        self.static_dir = STATIC_DIR
        self.js_dir = STATIC_DIR / "js"
        self.css_dir = STATIC_DIR / "css"

    def test_html_files_exist(self):
        """Verifica que los tres puntos de entrada HTML existan."""
        for html_name in ["controller.html", "viewer.html", "overlay.html"]:
            html_file = self.static_dir / html_name
            self.assertTrue(html_file.exists(), f"Falta el archivo {html_name}")
            self.assertGreater(html_file.stat().st_size, 0)

    def test_css_files_exist(self):
        """Verifica que los estilos modulares existan y tengan contenido."""
        expected_css = [
            "theme.css",
            "controller.css",
            "responsive.css",
            "overlay.css",
            "viewer.css",
        ]
        for css_name in expected_css:
            css_file = self.css_dir / css_name
            self.assertTrue(css_file.exists(), f"Falta el archivo CSS {css_name}")
            self.assertGreater(css_file.stat().st_size, 0)

    def test_js_modules_exist(self):
        """Verifica que todos los módulos JS existan."""
        expected_js = [
            self.js_dir / "state.js",
            self.js_dir / "overlay.js",
            self.js_dir / "viewer.js",
            self.js_dir / "modules" / "youtube.js",
            self.js_dir / "modules" / "obs.js",
            self.js_dir / "modules" / "spotify.js",
            self.js_dir / "modules" / "soundboard.js",
            self.js_dir / "modules" / "modals.js",
            self.js_dir / "modules" / "timer.js",
        ]
        for js_file in expected_js:
            self.assertTrue(js_file.exists(), f"Falta el archivo JS {js_file.name}")
            self.assertGreater(js_file.stat().st_size, 0)

    def test_html_references_exist_on_disk(self):
        """
        Escanea controller.html, viewer.html y overlay.html
        y comprueba que cada <link href="..."> y <script src="...">
        apunte a un archivo real que existe en static/.
        """
        for html_name in ["controller.html", "viewer.html", "overlay.html"]:
            html_path = self.static_dir / html_name
            content = html_path.read_text(encoding="utf-8")

            # Buscar <link rel="stylesheet" href="...">
            css_matches = re.findall(r'<link[^>]+href=["\']([^"\']+\.css)["\']', content)
            for href in css_matches:
                clean_href = href.lstrip("/")
                resolved = self.static_dir / clean_href
                self.assertTrue(
                    resolved.exists(),
                    f"En {html_name}, referencia rota a CSS: {href}"
                )

            # Buscar <script src="...">
            js_matches = re.findall(r'<script[^>]+src=["\']([^"\']+\.js)["\']', content)
            for src in js_matches:
                clean_src = src.lstrip("/")
                resolved = self.static_dir / clean_src
                self.assertTrue(
                    resolved.exists(),
                    f"En {html_name}, referencia rota a JS: {src}"
                )

    def test_responsive_css_contains_mobile_scale_variables(self):
        """Verifica que las variables de escala móvil estén presentes en responsive.css."""
        responsive_css = (self.css_dir / "responsive.css").read_text(encoding="utf-8")
        required_vars = [
            "--mobile-font-size",
            "--mobile-btn-min-height",
            "--mobile-input-min-height",
            "--mobile-sound-btn-height",
            "--mobile-sound-btn-font",
            "--mobile-clock-size",
        ]
        for var_name in required_vars:
            self.assertIn(var_name, responsive_css, f"Variable {var_name} no encontrada en responsive.css")

    def test_all_js_syntax_valid(self):
        """
        Verifica la sintaxis de todos los archivos .js con 'node --check' si node está instalado.
        """
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("Node.js no está instalado en el sistema, omitiendo check de sintaxis JS.")

        all_js_files = list(self.js_dir.rglob("*.js"))
        self.assertGreater(len(all_js_files), 0, "No se encontraron archivos JS para testear")

        for js_path in all_js_files:
            result = subprocess.run(
                [node_bin, "--check", str(js_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            self.assertEqual(
                result.returncode,
                0,
                f"Error de sintaxis en {js_path.name}:\n{result.stderr}"
            )


if __name__ == "__main__":
    unittest.main()

