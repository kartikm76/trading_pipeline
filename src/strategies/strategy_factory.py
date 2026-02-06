import logging
import strategies

logger = logging.getLogger(__name__)

class StrategyFactory:
    @staticmethod
    def get_strategy(config):
        """
        Dynamically instantiates the active strategy defined in config.yaml
        """
        # 1. Get the active strategy metadata from ConfigManager
        active_strategies = config.active_strategy_info
        if not active_strategies:
            raise ValueError("No active strategy found in config.yaml")

        # Get the first active strategy (assuming only one should be active)
        strategy_info = active_strategies[0]
        class_name = strategy_info.get('class')
        underlying = strategy_info.get('underlying')
        logger.info(f"Instantiating Strategy: {class_name} for Underlying: {underlying}")

        try:
            # 2. Look up the class in the strategies package
            strategy_class = getattr(strategies, class_name)

            # 3. Initialize with the underlying symbol from YAML
            return strategy_class(underlying=underlying)

        except AttributeError:
            logger.error(f"Strategy class {class_name} not found.")
            raise ImportError(f"Strategy class {class_name} not found.")