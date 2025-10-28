# ec_engine/ec_error
class ECError(Exception):
    pass
class ECError(Exception):
    """纠删码基础错误类"""
    pass

class InsufficientShardsError(ECError):
    """可用分片不足错误"""
    pass

class InvalidParameterError(ECError):
    """参数无效错误"""
    pass

class DecodeFailedError(ECError):
    """解码失败错误"""
    pass