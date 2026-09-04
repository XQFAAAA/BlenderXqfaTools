import sys
import struct
import os

# 每顶点字节数
BYTES_PER_VERTEX_BLEND_IN = 16   # Blend.buf:       4 * R8G8B8A8
BYTES_PER_VERTEX_BLEND_OUT = 32  # Blend_R16.buf:   4 * R16G16B16A16
BYTES_PER_VERTEX_VG = 16         # BlendRemapVertexVG.buf: 2 * R16G16B16A16


def convert_blend_buffer(blend_path, vg_path):
    folder = os.path.dirname(blend_path)
    output_path = os.path.join(folder, "Blend_R16.buf")

    # 读取源文件
    with open(blend_path, 'rb') as f:
        blend_data = f.read()
    with open(vg_path, 'rb') as f:
        vg_data = f.read()

    blend_size = len(blend_data)
    vg_size = len(vg_data)

    # 校验文件对齐
    if blend_size == 0 or blend_size % BYTES_PER_VERTEX_BLEND_IN != 0:
        print(f"[Error] {blend_path}: 文件大小异常 ({blend_size} 字节)，无法按 16 字节/顶点对齐。已跳过。")
        return
    if vg_size == 0 or vg_size % BYTES_PER_VERTEX_VG != 0:
        print(f"[Error] {vg_path}: 文件大小异常 ({vg_size} 字节)，无法按 16 字节/顶点对齐。已跳过。")
        return

    blend_count = blend_size // BYTES_PER_VERTEX_BLEND_IN
    vg_count = vg_size // BYTES_PER_VERTEX_VG

    if blend_count != vg_count:
        print(f"[Error] {folder}: Blend.buf 顶点数 ({blend_count}) 与 BlendRemapVertexVG.buf 顶点数 ({vg_count}) 不一致。已跳过。")
        return

    VERTEX_COUNT = blend_count
    print(f"[Info] {os.path.basename(folder)}: 识别到 {VERTEX_COUNT} 个顶点。")

    # --- 步骤 1：Blend.buf (R8) -> Blend_R16.buf (R16) ---
    # 输入为按顶点交错的布局，每个顶点 16 字节：
    #   [0:4]   ATTRIBUTE3  R8G8B8A8_UINT   骨骼索引 0
    #   [4:8]   ATTRIBUTE14 R8G8B8A8_UINT   骨骼索引 1
    #   [8:12]  ATTRIBUTE4  R8G8B8A8_UNORM  骨骼权重 0
    #   [12:16] ATTRIBUTE15 R8G8B8A8_UNORM  骨骼权重 1
    # 输出同样为按顶点交错的布局，每个顶点 32 字节：
    #   [0:8]   R16G16B16A16_UINT
    #   [8:16]  R16G16B16A16_UINT
    #   [16:24] R16G16B16A16_UNORM
    #   [24:32] R16G16B16A16_UNORM
    out = bytearray()
    for i in range(VERTEX_COUNT):
        v = blend_data[i * BYTES_PER_VERTEX_BLEND_IN : (i + 1) * BYTES_PER_VERTEX_BLEND_IN]

        # UINT 零扩展：8-bit 整数直接作为 16-bit 整数
        uint1 = struct.unpack('<4B', v[0:4])
        uint2 = struct.unpack('<4B', v[4:8])

        # UNORM 位复制 (x * 257)：保持浮点值不变 (x/255 == x*257/65535)
        unorm1 = tuple(x * 257 for x in v[8:12])
        unorm2 = tuple(x * 257 for x in v[12:16])

        out += struct.pack('<4H4H4H4H', *uint1, *uint2, *unorm1, *unorm2)

    with open(output_path, 'wb') as f:
        f.write(out)
    print(f"[Success] 步骤1: {os.path.basename(blend_path)} -> {os.path.basename(output_path)} ({VERTEX_COUNT * BYTES_PER_VERTEX_BLEND_OUT} 字节)")

    # --- 步骤 2：用 BlendRemapVertexVG.buf 替换 Blend_R16.buf 中的骨骼索引 ---
    # BlendRemapVertexVG.buf 每顶点 16 字节 = 2 * R16G16B16A16_UINT，
    # 正好对应 Blend_R16.buf 每个顶点前 16 字节，直接覆盖，原地修改不另存。
    with open(output_path, 'r+b') as f:
        r16 = bytearray(f.read())
        for i in range(VERTEX_COUNT):
            start = i * BYTES_PER_VERTEX_BLEND_OUT
            r16[start : start + BYTES_PER_VERTEX_VG] = vg_data[i * BYTES_PER_VERTEX_VG : (i + 1) * BYTES_PER_VERTEX_VG]
        f.seek(0)
        f.write(r16)
    print(f"[Success] 步骤2: 已将 {os.path.basename(vg_path)} 的骨骼索引写入 {os.path.basename(output_path)} (原地修改)")


def process_folder(root):
    # 递归查找同时包含 Blend.buf 与 BlendRemapVertexVG.buf 的目录，逐个处理
    for dirpath, dirnames, filenames in os.walk(root):
        has_blend = "Blend.buf" in filenames
        has_vg = "BlendRemapVertexVG.buf" in filenames
        if has_blend and has_vg:
            convert_blend_buffer(os.path.join(dirpath, "Blend.buf"),
                                 os.path.join(dirpath, "BlendRemapVertexVG.buf"))
        elif has_blend:
            print(f"[Warning] {dirpath}: 找到 Blend.buf 但缺少 BlendRemapVertexVG.buf，已跳过。")


def main():
    if len(sys.argv) < 2:
        print("用法: python BlendBufferrR8-R16.py <文件夹1> [文件夹2] ...")
        sys.exit(1)

    for arg in sys.argv[1:]:
        if os.path.isdir(arg):
            process_folder(arg)
        else:
            print(f"[Warning] 不是文件夹或不存在: {arg}")

if __name__ == '__main__':
    main()
