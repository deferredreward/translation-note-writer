import os
import sys
import json
import importlib.util
import types

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

modules_pkg = types.ModuleType('modules')
modules_pkg.__path__ = [os.path.join(ROOT_DIR, 'modules')]
sys.modules.setdefault('modules', modules_pkg)

def _load_module(fullname, filename):
    path = os.path.join(ROOT_DIR, 'modules', filename)
    spec = importlib.util.spec_from_file_location(fullname, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = module
    spec.loader.exec_module(module)
    return module

ConfigManager = _load_module('modules.config_manager', 'config_manager.py').ConfigManager
CacheManager = _load_module('modules.cache_manager', 'cache_manager.py').CacheManager
BatchProcessor = _load_module('modules.batch_processor', 'batch_processor.py').BatchProcessor


def test_translate_unknown_handling():
    """Ensure translate-unknown rows with matching headword are programmatic."""
    cache_dir = os.path.join(os.path.dirname(__file__), 'cache')
    os.makedirs(cache_dir, exist_ok=True)
    tw_path = os.path.join(cache_dir, 'tw_headwords.json')
    with open(tw_path, 'w', encoding='utf-8') as f:
        json.dump(["faithful"], f)

    config = ConfigManager()
    config.set('cache.cache_dir', cache_dir)
    cache_manager = CacheManager(config, None)
    processor = BatchProcessor(config, None, None, cache_manager)

    item = {
        'Explanation': 'translate-unknown',
        'GLQuote': 'He was very faithful to God',
        'Ref': '1:1',
        'AT': ''
    }

    prog, ai = processor._separate_items_by_processing_type([item])
    if len(prog) == 1 and not ai:
        print("✓ translate-unknown headword matched; item programmatic")
        return True
    else:
        print("✗ translate-unknown item not handled correctly")
        return False


if __name__ == "__main__":
    success = test_translate_unknown_handling()
    sys.exit(0 if success else 1)
