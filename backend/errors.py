class RecommenderConfigurationError(RuntimeError):
    pass


class RecommenderAPIError(RuntimeError):
    pass


class RecommenderTimeout(TimeoutError):
    pass
