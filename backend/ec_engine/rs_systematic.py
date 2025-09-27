# ec_engine/rs_systematic.py
from typing import List, Optional
from reedsolo import RSCodec
import os


def encode(data: bytes, k: int, m: int) -> List[bytes]:
    """
    系统码RS编码：输入原始 data，输出 k+m 个等长分片（前 k 个为数据片，后 m 个为校验片）
    """
    if k <= 0 or m <= 0:
        raise ValueError("k 和 m 必须为正整数")
    n = k + m
    # 计算数据片大小，并补零到 k * shard_size
    shard_size = (len(data) + k - 1) // k if len(data) else 1
    pad_len = k * shard_size - len(data)
    padded = data + (b"\x00" * pad_len)

    # 切成 k 片
    data_shards = [padded[i * shard_size:(i + 1) * shard_size] for i in range(k)]
    parity_shards = [bytearray(shard_size) for _ in range(m)]

    rsc = RSCodec(m)  # n = k+m, nsym=m
    # 按“列”做编码：每列 k 个数据符号 -> 追加 m 个奇偶校验
    for j in range(shard_size):
        msg = bytes(ds[j] for ds in data_shards)  # 长度 k
        codeword = rsc.encode(msg)  # 长度 k+m（系统码：前 k 原样，后 m 为奇偶）
        parity = codeword[k:]  # 取后 m 个
        for pi in range(m):
            parity_shards[pi][j] = parity[pi]

    return data_shards + [bytes(p) for p in parity_shards]


# ec_engine/rs_systematic.py

def decode(shards: List[Optional[bytes]], k: int, m: int, shard_size: int, original_size: int) -> bytes:
    """
    系统码RS解码：shards 长度应为 k+m，可包含 None；需保证有 >= k 片有效
    """
    if k <= 0 or m <= 0:
        raise ValueError("k 和 m 必须为正整数")
    n = k + m
    if len(shards) != n:
        # 允许传比 n 短，内部补 None
        tmp = [None] * n
        for i, s in enumerate(shards[:n]):
            tmp[i] = s
        shards = tmp

    # 标记擦除位置 & 规范化长度
    present = 0
    for i in range(n):
        s = shards[i]
        if s is not None:
            present += 1
            if len(s) < shard_size:
                shards[i] = s + b"\x00" * (shard_size - len(s))
            elif len(s) > shard_size:
                shards[i] = s[:shard_size]
    if present < k:
        raise ValueError("可用分片不足，无法恢复")

    rsc = RSCodec(m)

    out_data_cols = [[0] * k for _ in range(shard_size)]

    for j in range(shard_size):
        codeword = bytearray(n)
        erase_pos = []
        for i in range(n):
            b = shards[i][j] if shards[i] is not None and j < len(shards[i]) else 0
            codeword[i] = b
            if shards[i] is None:  # 简化擦除位置判断
                erase_pos.append(i)

        # 解码（带擦除位）
        try:
            # [✅ 核心修正]
            # reedsolo.decode 返回一个元组，我们只需要第一个元素（解码后的消息）。
            # 之前的代码将整个元组赋给了 msg，导致了后续的 TypeError。
            decoded_result = rsc.decode(bytes(codeword), erase_pos=erase_pos)

            # 为了代码健壮性，处理不同版本可能返回元组或直接返回 bytearray 的情况
            if isinstance(decoded_result, tuple):
                msg = decoded_result[0]  # 标准情况：取元组的第一个元素
            else:
                msg = decoded_result  # 兼容可能只返回消息本身的情况

        except Exception as e:
            # 提供更详细的错误日志以便调试
            print(f"[ERROR] Reedsolo decoding failed at column {j} with error: {e}")
            raise

        # 现在 msg 是一个 bytearray, msg[di] 会正确地返回一个整数 (0-255)
        for di in range(k):
            out_data_cols[j][di] = msg[di]

    # 重组原数据（按行展开前 k 个数据片）
    rebuilt = bytearray(k * shard_size)
    for i in range(k):
        for j in range(shard_size):
            # 此处现在可以正确工作，因为 out_data_cols[j][i] 是一个整数
            rebuilt[i * shard_size + j] = out_data_cols[j][i]

    return bytes(rebuilt[:original_size])