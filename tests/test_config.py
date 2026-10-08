"""Pruebas unitarias para config_manager.py."""
import unittest
import tempfile
import json
from pathlib import Path
import sys

# Añadir directorio raíz al path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config_manager import load_config, save_config, LOCAL_CONFIG_PATH, USER_CONFIG_PATH


class TestConfigManager(unittest.TestCase):
    """Casos de prueba para el gestor de configuración."""

    def setUp(self):
        """Configurar entorno de prueba con un archivo temporal."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_config = Path(self.temp_dir) / "test_config.json"
        
        # Guardar las rutas originales de config
        self.original_local_config = LOCAL_CONFIG_PATH
        self.original_user_config = USER_CONFIG_PATH
        
        # Crear config de prueba
        test_config = {
            "port": 8000,
            "obs_host": "localhost",
            "obs_port": 4455,
            "default_playback_rate": 1.7,
            "default_muted": True,
            "default_volume": 1.0,
        }
        
        with open(self.temp_config, 'w') as f:
            json.dump(test_config, f, indent=2)
        
        # Sobrescribir las rutas de config para usar el temporal
        import config_manager
        config_manager.LOCAL_CONFIG_PATH = self.temp_config
        config_manager.USER_CONFIG_PATH = Path(self.temp_dir) / "user_config.json"

    def tearDown(self):
        """Limpiar entorno de prueba."""
        import config_manager
        config_manager.LOCAL_CONFIG_PATH = self.original_local_config
        config_manager.USER_CONFIG_PATH = self.original_user_config
        
        if self.temp_config.exists():
            self.temp_config.unlink()
        if Path(self.temp_dir).exists():
            Path(self.temp_dir).rmdir()

    def test_load_config(self):
        """Probar carga de configuración."""
        config = load_config()
        
        self.assertIsInstance(config, dict)
        self.assertEqual(config.get("port"), 8000)
        self.assertEqual(config.get("obs_host"), "localhost")
        self.assertEqual(config.get("obs_port"), 4455)
        self.assertEqual(config.get("default_playback_rate"), 1.7)
        self.assertTrue(config.get("default_muted"))
        self.assertEqual(config.get("default_volume"), 1.0)

    def test_save_config(self):
        """Probar guardado de configuración."""
        # Modificar config
        new_values = {
            "port": 9000,
            "new_key": "test_value"
        }
        save_config(new_values)
        
        # Recargar y verificar
        config = load_config()
        self.assertEqual(config.get("port"), 9000)
        self.assertEqual(config.get("new_key"), "test_value")
        # Valores originales deben persistir
        self.assertEqual(config.get("obs_host"), "localhost")

    def test_save_config_persistence(self):
        """Probar que los cambios persisten entre cargas."""
        # Guardar valor nuevo
        save_config({"test_persistence": "persisted_value"})
        
        # Recargar
        config = load_config()
        self.assertEqual(config.get("test_persistence"), "persisted_value")

    def test_load_config_with_defaults(self):
        """Probar que se cargan valores por defecto si el archivo no existe."""
        # Eliminar config temporal
        if self.temp_config.exists():
            self.temp_config.unlink()
        
        # Crear config vacío
        config = load_config()
        
        # Verificar valores por defecto
        self.assertIsInstance(config, dict)
        self.assertIn("port", config)
        self.assertIn("obs_host", config)
        self.assertIn("obs_port", config)


if __name__ == '__main__':
    unittest.main()
