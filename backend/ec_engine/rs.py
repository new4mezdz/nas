import os
import math
import json
import datetime

from typing import List

from reedsolo import RSCodec

from .ec_error import ECError


def rs_encode(file_path: str, k: int, m: int, output_paths: List[str]):
    with open(file_path, 'rb') as f:
        content = f.read()

    block_size = math.ceil(len(content) / k)
    blocks = [content[i * block_size:(i + 1) * block_size] for i in range(k)]
    blocks[-1] += b'\x00' * (block_size - len(blocks[-1]))

    rsc = RSCodec(m)
    encoded = rsc.encode(b''.join(blocks))

    parity = encoded[k * block_size:]
    parity_block_size = math.ceil(len(parity) / m)
    parity_blocks = [parity[i * parity_block_size:(i + 1) * parity_block_size] for i in range(m)]

    for i in range(k):
        os.makedirs(os.path.join(output_paths[i], 'encoded'), exist_ok=True)
        with open(os.path.join(output_paths[i], 'encoded', f'data_{i}.blk'), 'wb') as f:
            f.write(blocks[i])

    for i in range(m):
        os.makedirs(os.path.join(output_paths[k + i], 'encoded'), exist_ok=True)
        with open(os.path.join(output_paths[k + i], 'encoded', f'parity_{i}.blk'), 'wb') as f:
            f.write(parity_blocks[i])

    meta = {
        'scheme': 'rs',
        'k': k,
        'm': m,
        'block_size': block_size,
        'original_size': len(content),
        'timestamp': datetime.now().isoformat(),
        'filename': os.path.basename(file_path)
    }
    with open(os.path.join(output_paths[0], 'encoded', 'meta.json'), 'w') as f:
        json.dump(meta, f)


def rs_decode(block_dirs: List[str], output_file: str, k: int, m: int):
    data_blocks, parity_blocks = [], []
    meta = None

    for d in block_dirs:
        meta_path = os.path.join(d, 'encoded', 'meta.json')
        if os.path.exists(meta_path):
            with open(meta_path, 'r') as f:
                meta = json.load(f)
            break

    if not meta:
        raise ECError("找不到元数据 meta.json")

    block_size = meta['block_size']
    original_size = meta['original_size']

    for d in block_dirs:
        folder = os.path.join(d, 'encoded')
        if not os.path.exists(folder): continue
        for f in os.listdir(folder):
            with open(os.path.join(folder, f), 'rb') as fin:
                if f.startswith('data_'):
                    data_blocks.append(fin.read())
                elif f.startswith('parity_'):
                    parity_blocks.append(fin.read())

    if len(data_blocks) + len(parity_blocks) < k:
        raise ECError("可用块不足，无法恢复")

    stream = b''.join(data_blocks[:k]) + b''.join(parity_blocks[:m])
    rsc = RSCodec(m)
    decoded = rsc.decode(stream)[0][:original_size]

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'wb') as f:
        f.write(decoded)
