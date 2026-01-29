class BronzeToSilverFilterPolicy:
    """
    Centralized repository of Business Rules.
    Pure strings. No infrastructure logic allowed here.
    """
    ZERO_DTE = "`Trade Date` = `Expiry Date`"
    OUT_OF_THE_MONEY = "Strike > UnderlyingPrice"  # Example
    HIGH_VOLATILITY = "iv > 0.50"                  # Example