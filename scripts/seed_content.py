"""Reproducibly write the curated two-week course and explicitly unproduced roadmap cards."""
from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.runner import DRILLS

def dump(group: str, name: str, value: dict) -> None:
    folder = ROOT / 'content' / group
    folder.mkdir(parents=True, exist_ok=True)
    (folder / (name+'.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

# Each tuple contains a distinct definition, failure, equation, budget, misconception.
LESSONS = [
 ('l0-memory','把显存拆成能核对的账', [
  ('单位与权重','显存账以字节为单位，参数量乘每元素字节数得到裸权重。','把十进制GB当成GiB会高估可用空间。8GB=7.45GiB【估算：8×10^9/2^30】，驱动与桌面仍需另扣。','符号表：P是参数数，b是每参数字节数，W是权重字节数。W=P×b。','随机模型0.5B【估算：500000000参数】以FP16存储时，权重0.93GiB【估算：500000000×2/2^30】；这是裸权重，不含激活。','以为模型文件小就能训练→实际梯度、优化器状态与临时张量也占空间。'),
  ('KV缓存','每层注意力把历史token的K与V保留下来，缓存随序列长度线性增长。','忽略KV会让长对话在权重能装下时仍然OOM；上下文加倍使缓存也加倍。','符号表：L为层数，T为token数，H为KV头数，D为头宽，b为字节数。KV=2×L×T×H×D×b。','取L=24、T=1024、H=8、D=64、b=2【估算：代入KV公式】，缓存48MiB【估算：2×24×1024×8×64×2/2^20】。GQA应填KV头数而非查询头数。','以为KV只与参数量有关→实际批量、上下文和KV头数共同决定缓存。'),
  ('训练状态','训练账必须按权重、梯度、优化器状态、激活、工作区逐项列出。','只算权重会遗漏Adam状态；FP32训练常驻项约为权重的四倍，激活还未计入。','符号表：P是参数数；纯FP32 Adam常驻字节M=16×P，来自权重、梯度与两份状态。','0.5B模型常驻约7.45GiB【估算：16×500000000/2^30】，在8GB机器上无激活余量；先用0.01B随机模型，常驻约0.15GiB【估算：16×10000000/2^30】，再测峰值。','以为混合精度总是只要半份内存→实际是否保留主权重取决于优化器实现。')],
  'def kv_bytes(layers, tokens, heads, head_dim, item_bytes):\n    return 2 * layers * tokens * heads * head_dim * item_bytes\n\nassert kv_bytes(24,1024,8,64,2) == 50331648',
  '裸权重、KV、训练状态分开记。半精度五亿参数裸权重约0.93GiB【估算：参数×字节】。示例KV为48MiB【估算：双缓存公式】。纯单精度Adam常驻约7.45GiB【估算：每参数十六字节】，所以先缩小随机模型再测峰值。'),
 ('l0-tensor','从形状到矩阵乘法契约', [
  ('形状契约','矩阵乘法要求左矩阵末维等于右矩阵倒数第二维，输出保留外侧维度。','广播与矩阵乘法混淆可能得到能运行却语义错的输出。','符号表：A为m×k，B为k×n，C为m×n。C[i,j]=sum(A[i,t]×B[t,j])。','m=32、k=64、n=16【估算：示例形状】，乘加按两次浮点操作计为65536FLOP【估算：2×32×64×16】。先核对形状再比较数值。','以为相同元素数即可相乘→实际收缩轴必须相同。'),
  ('步幅与视图','步幅描述索引增加时跨过的字节，转置可以只改步幅而不复制数据。','把视图当成独立副本，原地写入会改变源数组。连续化则可能新增完整副本。','符号表：偏移o=i×s0+j×s1，s是字节步幅。','形状1024×1024的FP32数组占4MiB【估算：1024×1024×4/2^20】；contiguous副本把这部分升到8MiB【估算：原件加副本】。Windows上先查strides与shares_memory。','以为转置必然搬数据→实际访问顺序变化也能变慢，复制要实测。'),
  ('误差容限','浮点结果用绝对误差加相对误差判断，比较基准必须写进契约。','只看相对误差会在真值接近零时失真；只看绝对误差会忽略大值尺度。','符号表：a为参考值，b为提交值。接受条件abs(a-b)≤atol+rtol×abs(a)。','验收使用atol=0.000001、rtol=0.00001【估算：本课程CPU数值契约】，不是所有精度通用的保证。先查shape与有限值，避免广播掩盖错维度。','以为allclose通过就证明算法正确→实际还需要边界、形状与数据分布覆盖。')],
  'import numpy as np\na = np.arange(6).reshape(2,3)\nb = np.ones((3,4))\nc = a @ b\nassert c.shape == (2,4)\nassert np.allclose(c, [[3]*4,[12]*4])',
  '矩阵收缩轴必须相等。示例运算是65536FLOP【估算：两倍三维乘积】。数组本体是4MiB【估算：元素数乘字节】，复制后翻倍。验收绝对容差0.000001【估算：课程契约】，同时检查形状与有限值。'),
 ('l0-softmax','稳定归一化与带宽账', [
  ('最大值平移','softmax把每行实数映射为总和为一的非负权重，减最大值保持结果不变。','直接求指数可能溢出；输入1000【估算：溢出示例】时应先减去该行最大值。','符号表：x为输入，m=max(x)，p[i]=exp(x[i]-m)/sum(exp(x-m))。','先用CPU float64验证稳定性，再考虑FP16；float64每元素8字节【文献：NumPy dtype itemsize定义】。不要为这个小实验加载GPU模型。','以为减最大值改变概率→实际分子分母被同一个因子缩放。'),
  ('归约轴','归约轴决定哪些元素共同归一化；batch维必须保持独立。','全张量归一化会让不同样本互相影响，行和不再满足契约。','符号表：X是B×N，m与分母均保留B×一列；axis=-1代表最后一轴。','形状256×256的float64输入占0.5MiB【估算：256×256×8/2^20】，中间结果必须纳入峰值；验收包含常数行与单元素行。','以为只要总和为一就够→实际每一行的和都必须为一。'),
  ('向量化与基线','向量化把Python循环转为数组运算；基线必须在同机同进程测量。','与异机数字比较无法分离硬件、线程和库版本影响。','符号表：S=t_base/t_new，t为相同输入下的中位耗时。','先预热2次，再重复7次【估算：本课程测量协议】，CPU同步执行，取中位数；目标加速至少1.2倍【估算：课程验收阈值】，并保留正确性门禁。','以为越短的单次耗时越可信→实际调度噪声可能主导微秒级结果。')],
  'import numpy as np\ndef softmax_rows(x):\n    z = x - np.max(x, axis=-1, keepdims=True)\n    e = np.exp(z)\n    return e / np.sum(e, axis=-1, keepdims=True)\nassert np.allclose(softmax_rows(np.zeros((2,3))).sum(-1), 1)',
  '先按行减最大值再指数。实验输入占0.5MiB【估算：形状乘元素字节】。计时预热2次【估算：协议】，重复7次【估算：协议】。同机循环基线作为分母，检查数值后才谈提速。'),
 ('l0-attention','注意力张量与缓存增长', [
  ('缩放点积','注意力先用Q与K的点积求权重，再对V做加权求和。','漏掉缩放会随着头宽增加使logit分布变尖锐，比较时不能只看输出形状。','符号表：Q、K、V为T×D，A=softmax(Q×K转置/sqrt(D))，O=A×V。','T=96、D=32【估算：验收输入】，CPU即可验证；此实验不含因果mask与多头，不能直接当作自回归推理服务。','以为输出与Q同形就正确→实际还要验证权重沿key轴归一化。'),
  ('平方中间量','直接计算注意力分数会产生随序列长度平方增长的中间矩阵。','把上下文加倍可能使分数矩阵增至四倍，KV却只增至两倍。','符号表：分数存储S=T×T×b，缓存存储C=2×L×T×H×D×b。','单头T=8192、FP16【估算：边界输入】的分数矩阵占128MiB【估算：8192×8192×2/2^20】；多头、batch与反向会继续放大，先做分块并逐项预算。','以为有KV缓存就没有平方计算→实际prefill与decode的张量形状不同。'),
  ('分块的代价','分块只保留部分分数，降低峰值但需要正确合并归一化统计量。','分别对块softmax再拼接会丢掉全局分母。','符号表：跨块最大值m=max(m_old,m_new)，旧分母必须乘exp(m_old-m)再合并。','设块宽256【估算：实验候选】可先在小输入对齐完整实现；本版验收完整CPU实现，不声称实现FlashAttention或给出GPU吞吐。','以为分块天然更快→实际小块会增加调度开销，先测再选。')],
  'import numpy as np\ndef attention(q,k,v):\n    s = q @ k.T / np.sqrt(q.shape[-1])\n    e = np.exp(s - s.max(-1, keepdims=True))\n    return (e/e.sum(-1, keepdims=True)) @ v\nr = np.random.default_rng(1)\nx = r.normal(size=(7,4))\nassert attention(x,x,x).shape == x.shape',
  '注意力有两个矩阵乘法。示例头宽32【估算：实验输入】用于缩放。长序列单头分数矩阵可达128MiB【估算：平方存储公式】。分块候选宽256【估算：实验候选】，合并时要维护全局最大值与分母。'),
 ('l0-measure','让每个性能数字能复跑', [
  ('时间协议','计时报告必须说明数据、预热、重复次数、统计量和同步方式。','异步GPU调用只量到提交时间会夸大加速；CPU与GPU计时不能混用。','符号表：t_med=median(t_i)，S=t_base/t_med。GPU应在计时边界同步。','当前lab是CPU NumPy同步执行：预热2次，重复7次【估算：课程协议】；CUDA未探测时不能把CPU耗时填作GPU吞吐。','以为第一次运行代表稳态→实际导入、分配与缓存预热会进入首轮。'),
  ('估算差异','理论估算是可复算模型，实测是具体机器和协议下的观测，二者要同时保存。','只保存最好的数字会丢失失败实验，后续无法解释回归。','符号表：差异δ=(measured-estimated)/abs(estimated)×百分比。估算为零时差异无定义。','差异绝对值大于30%【估算：课程记账门槛】时需额外说明；原因从缓存、带宽、精度、调度、测量误差中选择，不可只写“快了”。','以为超过估算就是实现错→实际模型可能漏掉缓存复用或库开销。'),
  ('本机基线','基线把机器指纹、版本、输入和协议与观测绑定，复跑才能判断稳定性。','拿桌面卡或别人的数字做分母，会让笔记本功耗与散热差异被误判为代码问题。','符号表：漂移r=abs(t_new-t_old)/t_old。峰值P取测量区间内最大值。','本机只记录内存复制基线与CPU lab基线，不编造RTX 5070 Laptop的FP16峰值；8GB【文献：用户提供的机器规格】是容量约束，实际可用量须诊断实测。','以为同一型号等于同一基线→实际功耗、温度、系统负载与线程配置都要记录。')],
  'import time, statistics\nimport numpy as np\nx = np.ones(1000000, dtype=np.float32)\nsamples = []\nfor _ in range(7):\n    start = time.perf_counter_ns()\n    y = x.copy()\n    samples.append((time.perf_counter_ns()-start)/1e6)\nassert statistics.median(samples) > 0',
  '每个数都带机器与协议。预热2次【估算：协议】再重复7次【估算：协议】。差异超过30%【估算：课程阈值】就补原因。GPU吞吐尚未实测时留空，先解释本机CPU结果。')]

def main() -> None:
    for index, (key, (signature, starter)) in enumerate(DRILLS.items()):
        dump('units', key, dict(id=key, order=index, week=1, layer='R0', unit=key, title=['稳定 softmax','矩阵乘法','逐行 LayerNorm','线性回归梯度','KV 字节账'][index], objective='从签名独立实现并通过隐藏边界测试', concepts=[signature.split('(')[0], '形状契约', '数值边界'], deliverable='单文件 NumPy 实现', acceptance_cmd=f'python -m app.runner accept {key} --solution {{solution}}', hours=dict(study=.3,write=1,read=.2), prereq=[] if not index else [list(DRILLS)[index-1]], gate=True, practice=key, lecture=False, produced=True))
    for index, (key, title, concepts, code, summary) in enumerate(LESSONS):
        previous = list(DRILLS)[-1] if not index else LESSONS[index-1][0]
        practice = ['r0-kv','r0-matmul','lab-softmax','lab-attention','lab-attention'][index]
        dump('units', key, dict(id=key, order=5+index, week=2, layer='L0', unit=key, title=title, objective=['独立算清权重、训练状态和KV缓存','核对形状、操作数和容差','实现稳定逐行softmax并测加速','实现缩放点积注意力并解释平方中间量','提交可复跑的理论与实测记录'][index], concepts=[c[0] for c in concepts], deliverable='讲义复述 + 五题闭卷 + 实验记录', acceptance_cmd=f'python -m app.runner accept {practice} --solution {{solution}}', hours=dict(study=.6,write=1.4,read=.4), prereq=[previous], gate=True, practice=practice, lecture=True, produced=True))
        sections = [f'# {title}\n\n## 0 速览\n\n用可执行数组实验核对{title}。容量上限8GB【文献：用户机器规格】，GPU可用量要扣除桌面与驱动。\n', f'## 1 心智模型\n\n先写输入输出契约，再列存储与运算账，最后对比本机观测。把每一次测量当成模型检验：如果单位不一致，差异比值没有意义。先用1个小数组【估算：最小复现策略】验证，再扩大形状。\n', '## 2 概念逐条\n']
        for name, definition, failure, math, budget, misconception in concepts:
            sections.append(f'### {name}\n\n定义：{definition}\n\n后果：{failure}\n\n数学：{math}\n\n工程后果：{budget}\n\n常见误解：{misconception}\n')
        sections += ['## 3 数字表\n\n'+'\n\n'.join(c[4] for c in concepts), '## 4 代码\n\n```python\n'+code+'\n```', '## 5 边界与失败模式\n\n先测空维度、常数行与大幅值输入；拒绝非有限值。若出现OOM，先将批量或上下文减半，再重新列出峰值账。内存限制256MiB【估算：CPU验收进程预算】不等于显存容量。', '## 6 三分钟复述稿\n\n'+summary, '## 7 自测\n\n闭卷解释本讲每个变量；手算讲义里的存储量；设计一次只改输入尺寸的对照实验。用5题自测【估算：课程题型约定】确认后再送验收。', '## 8 延伸阅读\n\n离线先运行上面的最小代码并查本机help(numpy)。可选在线原始资料仅列出，不在运行时请求：NumPy API reference（numpy.org/doc/stable/reference/）；PyTorch CUDA memory management（pytorch.org/docs/stable/notes/cuda.html）。', '## 9 术语表\n\nGiB：二进制容量单位；GB：十进制容量单位；KV：历史键和值；基线：同机对照实现；峰值：区间最大占用；同步：工作完成后才结束计时。']
        folder = ROOT/'content/lectures'
        folder.mkdir(parents=True, exist_ok=True)
        (folder/(key+'.md')).write_text('\n\n'.join(sections)+'\n', encoding='utf-8')
    layers = ['L1','L1','L2','L2','L3','L3','L4','L4','L5','L5']
    for week, layer in enumerate(layers, 3):
        key = f'week-{week:02}'
        dump('units', key, dict(id=key, order=week+20, week=week, layer=layer, unit=key, title=layer+' · 待生产', objective='待生产；通过内容工厂校验后才开放', concepts=[], deliverable='待生产', acceptance_cmd='', hours=dict(study=2,write=6,read=2), prereq=['l0-measure' if week==3 else f'week-{week-1:02}'], gate=True, practice='', lecture=False, produced=False))
    for key, title, signature, tree, seed in [('lab-softmax','逐行稳定 softmax','softmax_rows(x)','softmax_rows','x = rng.normal(size=(256,256))'), ('lab-attention','缩放点积注意力','attention(q, k, v)','attention','q,k,v = [rng.normal(size=(96,32)) for _ in range(3)]')]:
        dump('labs', key, dict(id=key,unit='l0-softmax' if key=='lab-softmax' else 'l0-attention', task=title, mechanism='实现数组算子，核对数值后与同机Python循环基线比较。CPU执行；GPU吞吐未测。',timebox_min=120 if key=='lab-softmax' else 150,env=dict(versions={'python':'3.11','numpy':'2.2.6'},vram_limit_mb=8192,env_vars={'OPENBLAS_NUM_THREADS':'1'},selfcheck_cmd='python run.py --selfcheck'),scaffold=dict(tree=['solution.py'],signatures=[signature],contract='float64输入，最后一轴归一化；输出shape必须匹配；禁止非有限值；CPU内存预算256MiB',seed_script='import numpy as np\nrng = np.random.default_rng(73)\n'+seed,edge_cases=['单元素/单token','常数行/负值','不同矩形维度'],starter=f'import numpy as np\n\ndef {signature}:\n    raise NotImplementedError\n'),stages=[{'goal':'形状与单位检查','expected_observation':'输出形状符合契约'}, {'goal':'正确性对齐','expected_observation':'边界与误差容限通过'}, {'goal':'性能与内存记账','expected_observation':'同机加速与预算均过线'}],acceptance=dict(cmd=f'python -m app.runner accept {key} --solution {{solution}}',correctness=dict(atol=1e-6,rtol=1e-5,dataset='deterministic seed 42; includes edge cases'),perf=dict(baseline='same-process Python loop',target_x=1.2,protocol=dict(warmup=2,reps=7,metric='median_ms',sync='CPU synchronous NumPy')),memory=dict(limit_mb=256,api='Windows peak_wset + tracemalloc, CPU not VRAM'),robustness=['singleton','constant/large values','shape and finite checks']),hints=[dict(after_min=m,level=i+1,content=h) for i,(m,h) in enumerate([(15,'先写形状注释与归约轴'),(40,'检查最大值平移与keepdims'),(75,'只替换最内层循环，复跑同机基线')])],symptoms=[dict(symptom=s,cause=c,fix=f) for s,c,f in [('溢出','直接指数','先减最大值'),('行和异常','归约轴错','保留维度'),('输出错维','转置遗漏','先写形状'),('速度倒退','重复分配','减少临时数组'),('内存超限','中间量过大','减小输入或分块并重算预算')]],scoring='四项均通过且实验账提交才通过',difficulty=dict(fill_in='提供签名与契约',from_scratch='仅签名和测试')))
    questions = [dict(id='c1',kind='concept',prompt='不用参考解释权重、KV、激活的区别。',rubric=['无法区分','能区分两项','能区分三项并说出增长规律']),dict(id='c2',kind='concept',prompt='解释为什么softmax减最大值不改变结果。',rubric=['没有解释','提到防溢出','说明分子分母同因子缩放']),dict(id='n1',kind='number',prompt='FP16的1024×1024数组占多少MiB？',answer=2,atol=.001,rtol=0,working='元素数×每元素字节数÷每MiB字节数；先统一单位再相乘。'),dict(id='n2',kind='number',prompt='L=24,T=1024,H=8,D=64,b=2，KV共多少MiB？',answer=48,atol=.01,rtol=0,working='键与值各一份，再乘层、token、KV头数、头宽和元素字节，最后换成MiB。'),dict(id='d1',kind='design',prompt='设计一次比较向量化与循环的实验。',rubric=['缺少对照','固定数据与同机对照','还明确预热、重复、中位数、内存与正确性门禁'])]
    dump('quizzes','l0-check',dict(id='l0-check',timebox_min=15,questions=questions))
    dump('quizzes','milestone-1',dict(id='milestone-1',timebox_min=40,questions=questions,pass_rule='计算题全对且折算总分至少4/5；概念和设计采用0/1/2自评，每题除以2'))
    import copy
    variants=[
      ('l0-memory','解释裸权重与Adam常驻项的差别。','解释KV为何随token数线性增长。','0.5B参数、每参数2字节，裸权重多少十进制GB？',1.,'参数数×每参数字节÷十进制GB字节数。','L=24,T=1024,H=8,D=64,b=2，KV共多少MiB？',48.,'K和V两份×层×token×KV头×头宽×字节，再换成MiB。'),
      ('l0-tensor','解释矩阵收缩轴与广播的区别。','解释转置视图为何可能影响源数组。','m=32,k=64,n=16，矩阵乘加计多少FLOP？',65536.,'把乘法与加法分别计一次，再乘输出行、收缩轴、输出列。','1024×1024个FP32元素占多少MiB？',4.,'元素数×每元素字节数，再除以MiB字节数。'),
      ('l0-softmax','解释减最大值为何保持softmax不变。','解释batch维与归约轴的区别。','256×256的float64输入占多少MiB？',.5,'行数×列数×每元素字节，再换算为MiB。','基线8ms，新实现2ms，加速多少倍？',4.,'基线耗时除以新实现耗时；使用相同单位。'),
      ('l0-attention','解释Q、K、V和输出的形状关系。','解释为什么分块后不能各自softmax再拼接。','8192×8192的FP16单头分数矩阵占多少MiB？',128.,'序列长度平方×每元素字节，再换成MiB。','只增加T到原来的2倍，分数矩阵容量增加到几倍？',4.,'把新长度代入平方存储公式，再除以原存储。'),
      ('l0-measure','说明GPU计时为何需要同步。','说明本机复制带宽为何不能当成GPU峰值。','实测13ms，估算10ms，差异百分比是多少？',30.,'实测减估算，除以估算绝对值，最后乘百分比。','预热2次后测7次，共调用几次？',9.,'预热调用数加测量调用数。')]
    for key,c1,c2,n1,a1,w1,n2,a2,w2 in variants:
        qs=copy.deepcopy(questions);qs[0]['prompt']=c1;qs[1]['prompt']=c2
        for q,prompt,answer,working in [(qs[2],n1,a1,w1),(qs[3],n2,a2,w2)]:q.update(prompt=prompt,answer=answer,working=working)
        dump('quizzes',key,dict(id=key,timebox_min=15,questions=qs))

if __name__ == '__main__':
    main()
    from annotate_content import annotate
    for path in (ROOT/'content/lectures').glob('*.md'):
        path.write_text(annotate(path.read_text(encoding='utf-8')),encoding='utf-8')
