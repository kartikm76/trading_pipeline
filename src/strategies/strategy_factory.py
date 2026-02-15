import logging
import strategies

logger = logging.getLogger(__name__)

class StrategyFactory:
    @staticmethod
    def get_strategy(strategy_name, config):
        """
        Dynamically instantiates the active strategy defined in config.yaml
        """
        # 1. Look up the specific strategy metadata
        strategy_info = next(
            (s for s in config.active_strategy_info if s.get('class') == strategy_name),
            None
        )
        if not strategy_info:
            raise ValueError(f"No strategy found for class {strategy_name} in config.yaml")

        underlying = strategy_info.get('underlying')

        try:
            # 2. Dynamic instantiation from the strategies package
            strategy_class = getattr(strategies, strategy_name)
            # 3. Initialize with the underlying symbol from YAML
            return strategy_class(config=config, underlying=underlying)
        except AttributeError:
            logger.error(f"Strategy class {strategy_name} not found.")
            raise ImportError(f"Strategy class {strategy_name} not found.")