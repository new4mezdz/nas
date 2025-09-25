# ec_engine/rs_systematic.py
from typing import List, Optional
from reedsolo import RSCodec

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
    data_shards = [padded[i*shard_size:(i+1)*shard_size] for i in range(k)]
    parity_shards = [bytearray(shard_size) for _ in range(m)]

    rsc = RSCodec(m)  # n = k+m, nsym=m
    # 按“列”做编码：每列 k 个数据符号 -> 追加 m 个奇偶校验
    for j in range(shard_size):
        msg = bytes(ds[j] for ds in data_shards)        # 长度 k
        codeword = rsc.encode(msg)                      # 长度 k+m（系统码：前 k 原样，后 m 为奇偶）
        parity = codeword[k:]                           # 取后 m 个
        for pi in range(m):
            parity_shards[pi][j] = parity[pi]

    return data_shards + [bytes(p) for p in parity_shards]

def decode(shards: List[Optional[bytes]], k: int, m: int, shard_size: int, original_size: int) -> bytes:
    """
    系统码RS解码：shards 长度应为 k+m，可包含 None；需保证有 >= k 片有效
    """
    if k <= 0 or m <= 0:
        raise ValueError("k 和 m 必须为正整数")
    n = k + m
    if len(shards) != n:
        # 允许传比 n 短，内部补 None
        tmp = [None]*n
        for i, s in enumerate(shards[:n]):
            tmp[i] = s
        shards = tmp

    # 标记擦除位置 & 规范化长度
    present = 0
    cols = []
    for i in range(n):
        s = shards[i]
        if s is not None:
            present += 1
            if len(s) < shard_size:
                s = s + b"\x00" * (shard_size - len(s))
            elif len(s) > shard_size:
                s = s[:shard_size]
            cols.append((i, s))
    if present < k:
        raise ValueError("可用分片不足，无法恢复")

    rsc = RSCodec(m)
    # 逐列恢复
    out_data_cols = [bytearray(k) for _ in range(shard_size)]
    for j in range(shard_size):
        codeword = bytearray(n)
        erase_pos = []
        for i in range(n):
            b = shards[i][j] if (i < len(shards) and shards[i] is not None) else 0
            codeword[i] = b
            if (i >= len(shards)) or (shards[i] is None):
                erase_pos.append(i)
        # 解码（带擦除位）
        msg, _ = rsc.decode(bytes(codeword), erase_pos=erase_pos)
        # msg 长度为 k（系统码）
        for di in range(k):
            out_data_cols[j][di] = msg[di]

    # 重组原数据（按行展开前 k 个数据片）
    # 先把 k 个数据片拼回原顺序
    rebuilt = bytearray(k * shard_size)
    for i in range(k):
        for j in range(shard_size):
            rebuilt[i*shard_size + j] = out_data_cols[j][i]

    return bytes(rebuilt[:original_size])
