---
name: "wwmi-merged-instance-converter"
description: "将 WWMI 旧版 Merged 骨架 mod 升级为 Merged Instance 多实例新版 mod（含 13 项 ini 变更，基于 $instance_id + TextureOverrideMeshDataCB 方案），并按 BlendBufferrR8-R16.py 由 Blend.buf + BlendRemapVertexVG.buf 生成 Blend_R16.buf。当需要把旧版 mod 转成支持同屏多实例/16 位骨骼索引的新版 mod 时使用。"
---

# WWMI Merged Instance 转换指南

把一个使用 **Merged（合并）骨架**的旧版 WWMI mod 升级为 **Merged Instance（多实例合并骨架）** 新版 mod，并生成配套的 16 位混合缓冲 `Blend_R16.buf`。

## 何时使用

当用户要求把旧版 mod（仅支持同屏 1 个 mod 对象、blend 使用 8 位索引）转换为新版（支持同一对象多个实例、骨骼/顶点组索引突破 256 限制使用 16 位）时使用。

参考对照文件（均已复制到本 skill 的 `references/` 文件夹，Test 对象 = 8 组件、实例数=8）：
- 旧版：`references/mod.bak`（Merged 模式）
- 新版：`references/mod.ini`（Merged Instance，`$instance_id` 方案）
- 转换脚本：`references/BlendBufferrR8-R16.py`
- 缓冲样本：`references/Blend.buf`、`references/BlendRemapVertexVG.buf`（输入）→ `references/Blend_R16.buf`（输出）

## 背景

- 旧版 mod.ini 使用单份骨架缓冲 `ResourceMergedSkeleton` / `ResourceExtraMergedSkeleton`，同屏出现多个同对象实例时会互相覆盖。
- 新版通过 **Pool（资源池）+ `$instance_id`（实例 ID）** 为每个实例分配独立骨架合并槽位，并改用 16 位 blend 数据（`Blend_R16.buf`）支持超过 256 的 VG/骨骼索引。
- 实例 ID 的获取：`[TextureOverrideMeshDataCB]`（通用 hash `358d62cb`）把 MeshDataCB 标记为 `3380.7777`；在每个组件绘制处理开头，从 vs-cb2/vs-cb3（若等于 3380.7777）把 `@vs-cb2`/`@vs-cb3`（当前绑定 CB 的地址，不同实例不同）写入通用变量 `$instance_id`。

## 变量约定

- `N`：实例数量，实例编号 `0 .. N-1`（Test 参考中 N=8）
- `C`：组件数量，组件编号 `0 .. C-1`（Test 参考中 C=8）
- `$instance_id`：当前绘制调用的实例 ID（通用变量，从标记的 MeshDataCB 捕获，供 CommandListMergeSkeleton / OverrideSharedResources 使用）
- `$instance_id_{N}`：第 N 个实例的实例 ID（在帧末用于选择该实例的 Pool 槽位）
- `$merge_status_id_{C}_{N}`：组件 C 在实例 N 的骨架合并状态（0/1/2）

## 转换流程（含备份前置步骤）

按以下顺序执行：

1. **备份旧版 ini（前置步骤）**
   - 若目标 `mod.ini` 存在且内容仍为旧版（Merged），先将其复制为 `mod.bak` 作备份，再执行后续改写，避免旧版内容丢失。
   - 若 `mod.bak` 已存在，则直接覆盖（以本次备份为准）或保留时间戳副本。
2. **生成 16 位混合缓冲**
   - 依据 `references/BlendBufferrR8-R16.py`，由 `Meshes/Blend.buf` + `Meshes/BlendRemapVertexVG.buf` 生成 `Meshes/Blend_R16.buf`（详见「二、Blend_R16.buf 生成」）。
3. **改写 ini**
   - 按下方「一、INI 变更」的 13 项逐条把旧版内容改写为 Merged Instance 新版。
4. **写入 mod.ini**
   - 将新版内容写入 `mod.ini`。
5. **验证**
   - 对照「三、检查清单」逐项检查，确认转换正确。

---

## 一、INI 变更（旧版 Merged → 新版 Merged Instance）

### 1. Constants：merge_status_id 按 组件×实例 展开

旧版（每组件一个）：
```
global $merge_status_id_0 = 0
...
global $merge_status_id_7 = 0
```

新版（每实例一组，共 C×N 个）：
```
global $merge_status_id_0_0 = 0
...
global $merge_status_id_7_0 = 0
global $merge_status_id_0_1 = 0
...
global $merge_status_id_7_1 = 0
...
```
作用：让每个实例只进入一次骨骼合并流程，避免重复计算。实例数增加时变量组数对应增加。

### 2. Constants：新增通用实例 ID 变量

```
global $instance_id = 0        ; 当前绘制的实例 ID（通用）
global $instance_id_0 = 0      ; 每实例一个
global $instance_id_1 = 0
...
global $instance_id_7 = 0
```

### 3. 新增 [TextureOverrideMeshDataCB] 标记

在 `[TextureOverrideMarkBoneDataCB]` 之后新增（hash `358d62cb` 为 WuWa 通用 MeshDataCB hash）：
```
[TextureOverrideMeshDataCB]
hash = 358d62cb
match_priority = 0
filter_index = 3380.7777
```
作用：把 MeshDataCB 标记为 `3380.7777`，后续可通过 `vs-cb2 == 3380.7777` / `vs-cb3 == 3380.7777` 判断当前绘制调用是否携带该 CB。

### 4. 每个组件捕获 $instance_id

在 `TextureOverrideComponent{C}` 的 `if $mod_enabled` 之后、pool 初始化之前加入：
```
if vs-cb2 == 3380.7777
    $instance_id = @vs-cb2
elif vs-cb3 == 3380.7777
    $instance_id = @vs-cb3
endif
```
作用：把当前 drawcall 的实例 ID 记录到通用 `$instance_id`。
原因：到 Present 帧末执行骨骼矩阵传递时，已经拿不到之前 drawcall 的 vs-cb2/vs-cb3，必须提前记录。`@vs-cb2`/`@vs-cb3` 是当前绑定 CB 的资源地址，不同实例的 CB 地址不同，可唯一标识实例。

### 5. 帧末重置 merge_status_id

`CommandListUpdateMergedSkeleton` 中把全部 `$merge_status_id_{C}_{N}` 重置为 0（每个实例逐组件一行）。

### 6. 帧末按实例传递骨骼矩阵

旧版：
```
ResourceMergedSkeleton = copy ResourceMergedSkeletonRW
ResourceExtraMergedSkeleton = copy ResourceExtraMergedSkeletonRW
```

新版（基底 copy 保留，另加每实例一行）：
```
ResourceMergedSkeleton = copy ResourceMergedSkeletonRW
ResourceExtraMergedSkeleton = copy ResourceExtraMergedSkeletonRW
PoolMergedSkeleton[$instance_id_0] = copy PoolMergedSkeletonRW[$instance_id_0]
PoolExtraMergedSkeleton[$instance_id_0] = copy PoolExtraMergedSkeletonRW[$instance_id_0]
PoolMergedSkeleton[$instance_id_1] = copy PoolMergedSkeletonRW[$instance_id_1]
PoolExtraMergedSkeleton[$instance_id_1] = copy PoolExtraMergedSkeletonRW[$instance_id_1]
...
```

### 7. CommandListMergeSkeleton：按 $instance_id 区分实例

旧版直接写入单一 `ResourceMergedSkeletonRW` / `ResourceExtraMergedSkeletonRW`。

新版先初始化 pool 槽位，再按实例号选择输出缓冲（Regular 骨架部分）：
```
if $merge_status_id == 0
	if vs-cb4 == 3381.7777
		cs-cb8 = ref vs-cb4
        if #PoolMergedSkeletonRW[$instance_id] == -1
            PoolMergedSkeletonRW[$instance_id] = copy ResourceMergedSkeletonRW
        endif
        if #PoolMergedSkeletonRW[$instance_id] == 0
            $instance_id_0 = $instance_id
            cs-u6 = ResourceMergedSkeletonRW0
            $\WWMIv1\custom_mesh_scale = 1.00
            run = CustomShader\WWMIv1\SkeletonMerger
            PoolMergedSkeletonRW[$instance_id] = ref ResourceMergedSkeletonRW0
        elif #PoolMergedSkeletonRW[$instance_id] == 1
            $instance_id_1 = $instance_id
            cs-u6 = ResourceMergedSkeletonRW1
            $\WWMIv1\custom_mesh_scale = 1.00
            run = CustomShader\WWMIv1\SkeletonMerger
            PoolMergedSkeletonRW[$instance_id] = ref ResourceMergedSkeletonRW1
        ...
        endif
		$merge_status_id = 1
	endif
endif
```
Special（Extra）骨架部分同理：用 `PoolExtraMergedSkeletonRW[$instance_id]` 与 `ResourceExtraMergedSkeletonRW{N}`，判定条件 `vs-cb4 == 3381.7777 && vs-cb3 == 3381.7777`。

### 8. CommandListOverrideSharedResources：vb4 改 16 位 + 按实例绑定骨架

旧版：`vb4 = ResourceBlendBuffer`；`vs-cb4 = ref ResourceMergedSkeleton`（含 blend remap 分支）。

新版：
```
vb4 = ResourceBlendBuffer_R16
vb4->ElementFormat(ATTRIBUTE, 3) = R16G16B16A16_UINT
vb4->ElementFormat(ATTRIBUTE, 14) = R16G16B16A16_UINT
vb4->ElementFormat(ATTRIBUTE, 4) = R16G16B16A16_UNORM
vb4->ElementFormat(ATTRIBUTE, 15) = R16G16B16A16_UNORM
vb4->ElementOffset(ATTRIBUTE, 3) = 0
vb4->ElementOffset(ATTRIBUTE, 14) = 8
vb4->ElementOffset(ATTRIBUTE, 4) = 16
vb4->ElementOffset(ATTRIBUTE, 15) = 24
if vs-cb4 == 3381.7777
    vs-cb4 = ref PoolMergedSkeleton[$instance_id]
    if vs-cb3 == 3381.7777
        vs-cb3 = ref PoolExtraMergedSkeleton[$instance_id]
    endif
elif vs-cb3 == 3381.7777
    vs-cb3 = ref PoolMergedSkeleton[$instance_id]
endif
```

### 9. TextureOverrideComponent{C}：每个实例只进一次合并

在捕获 `$instance_id`（见第 4 项）之后，先初始化 pool 槽位：
```
if #PoolMergedSkeletonRW[$instance_id] == -1
    PoolMergedSkeletonRW[$instance_id] = copy ResourceMergedSkeletonRW
endif
```
再为每个实例各写一个独立的合并状态块：
```
if #PoolMergedSkeletonRW[$instance_id] == 0
    if $merge_status_id_{C}_0 != 2
        $\WWMIv1\vg_offset = <该组件vg_offset>
        $\WWMIv1\vg_count = <该组件vg_count>
        $merge_status_id = $merge_status_id_{C}_0
        run = CommandListMergeSkeleton
        $merge_status_id_{C}_0 = $merge_status_id
    endif
endif
if #PoolMergedSkeletonRW[$instance_id] == 1
    if $merge_status_id_{C}_1 != 2
        ...
    endif
endif
...
```

### 10. 资源池声明（随实例数增加）

```
[PoolMergedSkeleton]
pool_size = 8
pool_index_type = fifo
pool_lazy_initialization = 0

[PoolExtraMergedSkeleton]
pool_size = 8
pool_index_type = fifo
pool_lazy_initialization = 0

[PoolMergedSkeletonRW]
pool_size = 8
pool_index_type = fifo
pool_lazy_initialization = 0

[PoolExtraMergedSkeletonRW]
pool_size = 8
pool_index_type = fifo
pool_lazy_initialization = 0
```
（`pool_size` = 实例数 N。）

并为每个实例新增骨架缓冲（每实例各两份）：
```
[ResourceMergedSkeleton0]
[ResourceMergedSkeletonRW0]
type = RWBuffer
format = R32G32B32A32_FLOAT
array = 1536

[ResourceExtraMergedSkeleton0]
[ResourceExtraMergedSkeletonRW0]
type = RWBuffer
format = R32G32B32A32_FLOAT
array = 1536
...
```
基底 `[ResourceMergedSkeletonRW]` / `[ResourceExtraMergedSkeletonRW]` 保留并 `array = 1536`。

### 11. 绘制判断条件变更

旧版：`if ResourceMergedSkeleton !== null`
新版：`if #PoolMergedSkeleton[$instance_id] !== -1`

### 12. 删除压缩骨骼相关代码

因为索引/权重已突破 1 字节（256 个）限制，取消压缩骨骼索引和压缩骨骼矩阵的代码：
- 注释/删除 `CommandListInitializeBlendRemaps`（blend remap 初始化）
- 注释/删除 `CommandListRemapMergedSkeleton`（SkeletonRemapper 骨骼重映射）
- 删除 `ResourceBlendBufferNoStride`、`ResourceRemappedBlendBufferRW`、`ResourceRemappedSkeletonRW`、`ResourceExtraRemappedSkeletonRW` 等重映射资源
- 删除各组件节中的 `ResourceBlendBufferOverride` / `ResourceRemappedSkeletonComponent{C}` 绑定
- `BlendRemapVertexVG.buf` / `BlendRemapForward.buf` / `BlendRemapReverse.buf` 的资源声明可保留（不再参与计算）

### 13. 新增资源 [ResourceBlendBuffer_R16]

```
[ResourceBlendBuffer_R16]
type = Buffer
format = DXGI_FORMAT_R16_UINT
stride = 32
filename = Meshes/Blend_R16.buf
```

---

## 二、Blend_R16.buf 生成（依据 BlendBufferrR8-R16.py）

### 输入
- `Blend.buf`：16 字节/顶点 = 4×R8G8B8A8（8 个 8 位骨骼索引 + 8 个 8 位骨骼权重）
  - [0:4] 索引0-3（R8G8B8A8_UINT）
  - [4:8] 索引4-7（R8G8B8A8_UINT）
  - [8:12] 权重0-3（R8G8B8A8_UNORM）
  - [12:16] 权重4-7（R8G8B8A8_UNORM）
- `BlendRemapVertexVG.buf`：16 字节/顶点 = 2×R16G16B16A16（8 个 16 位 VG id）

### 输出
`Blend_R16.buf` 32 字节/顶点：
- [0:8] R16G16B16A16_UINT — 索引0-3（来自 BlendRemapVertexVG）
- [8:16] R16G16B16A16_UINT — 索引4-7（来自 BlendRemapVertexVG）
- [16:24] R16G16B16A16_UNORM — 权重0-3（Blend 权重 × 257）
- [24:32] R16G16B16A16_UNORM — 权重4-7（Blend 权重 × 257）

### 算法步骤
1. 校验两个文件分别按 16 字节/顶点对齐，且顶点数一致。
2. 8 位索引零扩展为 16 位（`struct.unpack('<4B')` → 直接作为 16 位整数）。
3. 8 位 UNORM 权重位复制为 16 位：`x * 257`（保持浮点值不变：x/255 == x*257/65535）。
4. 将每个顶点前 16 字节（索引部分）用 BlendRemapVertexVG.buf 的 16 位 VG id 覆盖。

### Python 实现（与脚本一致）
```python
import struct

BYTES_PER_VERTEX_BLEND_IN = 16
BYTES_PER_VERTEX_BLEND_OUT = 32
BYTES_PER_VERTEX_VG = 16

with open('Blend.buf', 'rb') as f:
    blend_data = f.read()
with open('BlendRemapVertexVG.buf', 'rb') as f:
    vg_data = f.read()

VERTEX_COUNT = len(blend_data) // BYTES_PER_VERTEX_BLEND_IN
assert len(blend_data) % BYTES_PER_VERTEX_BLEND_IN == 0
assert len(vg_data) % BYTES_PER_VERTEX_VG == 0
assert VERTEX_COUNT == len(vg_data) // BYTES_PER_VERTEX_VG

# 步骤1：R8 -> R16
out = bytearray()
for i in range(VERTEX_COUNT):
    v = blend_data[i * 16 : (i + 1) * 16]
    uint1 = struct.unpack('<4B', v[0:4])        # 索引0-3
    uint2 = struct.unpack('<4B', v[4:8])        # 索引4-7
    unorm1 = tuple(x * 257 for x in v[8:12])    # 权重0-3
    unorm2 = tuple(x * 257 for x in v[12:16])   # 权重4-7
    out += struct.pack('<4H4H4H4H', *uint1, *uint2, *unorm1, *unorm2)

with open('Blend_R16.buf', 'wb') as f:
    f.write(out)

# 步骤2：用 BlendRemapVertexVG.buf 覆盖索引部分（原地修改）
with open('Blend_R16.buf', 'r+b') as f:
    r16 = bytearray(f.read())
    for i in range(VERTEX_COUNT):
        start = i * BYTES_PER_VERTEX_BLEND_OUT
        r16[start : start + BYTES_PER_VERTEX_VG] = vg_data[i * BYTES_PER_VERTEX_VG : (i + 1) * BYTES_PER_VERTEX_VG]
    f.seek(0)
    f.write(r16)
```

---

## 三、检查清单

- [ ] Constants 中 `$merge_status_id_{C}_{N}` 数量 = 组件数 × 实例数
- [ ] 存在通用 `$instance_id` 变量 + 每实例 `$instance_id_{0..N-1}` 变量
- [ ] 存在 `[TextureOverrideMeshDataCB]`（hash = 358d62cb，filter_index = 3380.7777）
- [ ] 每个 `TextureOverrideComponent{C}` 都有 `$instance_id` 捕获块（vs-cb2/vs-cb3 == 3380.7777）
- [ ] `CommandListMergeSkeleton` 中每个实例分支都有 `$instance_id_{N} = $instance_id`，pool 访问用 `[$instance_id]`
- [ ] 帧末 `CommandListUpdateMergedSkeleton` 重置所有 merge_status_id，并按实例 copy Pool 骨架
- [ ] 每个 `TextureOverrideComponent{C}` 有 pool 槽位初始化 + 每个实例独立的合并状态块
- [ ] 绘制条件为 `if #PoolMergedSkeleton[$instance_id] !== -1`
- [ ] vb4 使用 `ResourceBlendBuffer_R16` 并带 4 条 ElementFormat + 4 条 ElementOffset
- [ ] 4 个 Pool 资源 `pool_size = 实例数`
- [ ] 每个实例的 `ResourceMergedSkeletonRW{N}` / `ResourceExtraMergedSkeletonRW{N}` 存在
- [ ] blend remap / 压缩骨骼相关代码已移除
- [ ] `Meshes/Blend_R16.buf` 已生成，且 `Blend.buf` 与 `BlendRemapVertexVG.buf` 顶点数一致
