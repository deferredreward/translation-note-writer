
  from modules.cache_manager import CacheManager
  from modules.sheet_manager import SheetManager
  from modules.config_manager import ConfigManager

  config = ConfigManager()
  sheet_manager = SheetManager(config)
  cache_manager = CacheManager(config, sheet_manager)

  try:
      # Force fetch biblical text for editor3/oba
      from modules.processing_utils import ensure_biblical_text_cached
      from modules.logger import setup_logging
      logger = setup_logging(config)

      ensure_biblical_text_cached('editor3', 'oba', cache_manager, sheet_manager, config, logger)
      print('✅ Biblical text caching attempted')
  except Exception as e:
      print(f'❌ Failed: {e}')
      import traceback
      traceback.print_exc()
