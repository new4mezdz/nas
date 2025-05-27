from .rs import rs_encode, rs_decode
from .ec_error import ECError

encoders = {
    'rs': rs_encode,
}

decoders = {
    'rs': rs_decode,
}

def encode(scheme, file_path, k, m, output_paths):
    if scheme not in encoders:
        raise ECError(f"不支持的编码方案: {scheme}")
    return encoders[scheme](file_path, k, m, output_paths)

def decode(scheme, block_dirs, output_path, k, m):
    if scheme not in decoders:
        raise ECError(f"不支持的解码方案: {scheme}")
    return decoders[scheme](block_dirs, output_path, k, m)
