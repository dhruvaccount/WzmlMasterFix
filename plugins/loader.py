import importlib
import inspect
import logging
from pathlib import Path

from core.registry import get_registry, PluginMetadata
from plugins.base import PluginBase

logger = logging.getLogger("wzml.plugins.loader")


def load_all_plugins():
    registry = get_registry()
    plugins_dir = Path(__file__).parent
    loaded_count = 0

    for category in ["downloader", "uploader", "processor"]:
        category_dir = plugins_dir / category
        if not category_dir.exists():
            continue

        for file_path in category_dir.glob("*.py"):
            if file_path.name == "__init__.py":
                continue

            module_name = f"plugins.{category}.{file_path.stem}"
            try:
                module = importlib.import_module(module_name)

                # Find plugin classes
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (
                        issubclass(obj, PluginBase)
                        and obj is not PluginBase
                        and getattr(obj, "name", "")
                    ):
                        # Only instantiate if defined in this module
                        if obj.__module__ == module_name:
                            plugin_name = obj.name
                            plugin_type = getattr(obj, "plugin_type", category)
                            full_name = f"{plugin_type}.{plugin_name}"

                            metadata = PluginMetadata(
                                name=plugin_name,
                                plugin_type=plugin_type,
                            )
                            instance = obj()
                            registry.register_plugin(full_name, metadata, instance)

                            # Also register without prefix if it's the first one, for backwards compatibility
                            if not registry.plugin_exists(plugin_name):
                                registry.register_plugin(
                                    plugin_name, metadata, instance
                                )

                            logger.info(
                                f"Registered plugin: {full_name} from {module_name}"
                            )
                            loaded_count += 1
            except Exception as e:
                logger.error(f"Error loading plugin {module_name}: {e}")

    return loaded_count
