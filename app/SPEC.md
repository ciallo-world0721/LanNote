# LanNote 探索版（explore/live）

把主线 `app/` 的双栏笔记和 `explore/integration/` 的 loro + WebSocket 协作合成一个可运行版本，
产出 `explore/live/LanNote探索版.exe`。`app/` 一行不动，`explore/integration/` 只读参考。

## 一、共享流程（UI）

1. 主窗口顶栏右侧一个「共享」按钮（两个字），跟现有 `tb` 按钮同风格。
2. 点「共享」：
   - 当前没有打开笔记：提示「先打开一条笔记」。
   - 未共享：弹出共享面板（非模态 `QDialog`，`Qt.Tool`，可同时操作主窗口）。
3. 面板第一步：显示当前网络（WiFi SSID；读不到就显示「有线/未知网络」+ 本机 IP），
   按钮「确认共享」「取消」。
4. 点「确认共享」进入第二步：
   - 没有 peer：显示「正在搜索…」。
   - 有 peer：列出已连接用户的完整名字（名字本身 ≤5 字），继续发现，后来的人自动加入。
   - 按钮：「收起」只隐藏面板，共享继续；发起者「关闭共享」结束整个会话；
     受邀者显示「退出共享」，只退出自己。
   - 面板右上角 X 等同于「收起」，**不是停止**。
5. 共享中顶栏按钮变成「共享中」，点它重新打开面板；左上角头像右下角一个小绿点。
6. 共享笔记 = 点「共享」时当前打开的那条。受邀者加入后自动打开同一条；
   本地没有就插一条（uid 用发起者的），有同 uid 就用发起者快照替换正文。
7. 发起者「关闭共享」：所有人退出共享，各自保留最新正文。
8. 发起者掉线/退出程序：其他人结束会话并保留最新正文。

## 二、身份

- 左上角删掉「全部」，换成头像圈（名字首字，颜色底）+ 名字（≤5 字）。
  点它改名，落到 `settings` 表；颜色同样持久化。
- 共享时广播 name/color；自己永远不画标记，只画别人。
- 名字默认取系统用户名截前 5 字；空名不允许。

## 三、列表与编辑区

- 左栏保持现在三行（标题/摘要/日期），选中行底色不变。
- 标题行右侧显示此刻在这条笔记里的其他人：彩色圆圈 + 名字首字，最多 3 个，超出显示 `+N`。
  **必须实时刷新**，即使当前没打开这条笔记。
- 编辑区里，对方光标位置画同色圆圈 + 首字；不画段主方块、不画名字气泡。
  对方切到别的笔记/离开，标记立刻消失。
- 空态（没选中笔记）：右栏保持空白提示，视觉上失焦（整体变淡），不抢焦点。

## 四、数据

- `notes` 表加 `uid TEXT NOT NULL DEFAULT ''`；旧库迁移时逐行生成 `uuid4().hex`。
  `create()` 生成 uid，`notes()`/`get()` 返回 uid。
- 共享笔记以发起者 uid 为准。受邀者本地没有则插入；有同 uid 则用发起者快照替换正文。
- 正文以纯文本为准；loro 快照只在会话内存在，不落库。
- 身份和颜色存 `settings(key TEXT PRIMARY KEY, value TEXT)`。

## 五、网络

- 复用 `explore/integration/` 的 `disc.py`、`net.py`、`wire.py`；同一局域网点共享就进同一个池，
  不需要房间名，`rid = room_id("lannote-share")` 固定。
- 消息：沿用 HS_REQ/HS_OK/HS_NO/PING/PONG/CUR/UPD/SNAP，新增
  `HELLO {iid,name,color,note,role,started}`、`PRESENCE {name,color,note,role}`、
  `NEED {note}`、`NOTE {note,title,color,data}`、`END {}`。
- 发起者：点共享时没有已连 peer 就是 host；连上已有 host 就是 guest。
- 同时点共享：`started` 早的当 host，相同则 iid 小的当 host；后到的 host 降为 guest，
  发 `NEED` 拿对方笔记。这一点写进 README 的已知限制。
- 72 小时内不做加密、不做房间口令、不做跨网段。

## 六、技术复用

- `doc.py`：从 integration 搬 `SharedDoc`，**删掉 paras/claim 和段主**，只保留文本、快照、光标、undo/redo。
- `bridge.py`：搬 `Editor`/`Bridge`/`PeerLayer`。`PeerLayer` 改成只画对方光标处的圆圈+首字，
  保留远端选区淡色底；不画段主方块。
- `net.py`/`disc.py`：搬过来，去掉 room 参数或固定 room；线程模型不变（QThread + queue + 20ms pump）。
- `mainwin.py`：从 app/ 复制后改：
  - 顶栏右侧加「共享」；「全部」换成身份块。
  - `Row` delegate 增加 peers 圆圈绘制。
  - 打开笔记时若 uid == 会话共享笔记，绑定 Bridge/PeerLayer；否则用原来的 QTextEdit 逻辑。
  - 切走共享笔记时解绑编辑器但保留会话 doc，继续接收 UPD。
  - 共享中撤销/重做接 `doc.undo/redo`；不共享时接控件自带栈。
  - 空态页加淡出效果。
- `store.py`：从 app/ 复制后加 uid、settings；迁移旧库。
- `theme.py`：配色+图标；新增 peer 调色板（6 色）和头像绘制 helper。

## 七、文件

```
explore/live/
  main.py          入口 + 单实例 + 托盘（沿用 app/main.py 结构）
  mainwin.py       双栏主窗口 + 共享入口
  store.py         SQLite（uid / settings）
  theme.py         配色、图标、头像
  doc.py           SharedDoc（无段主）
  bridge.py        Editor / Bridge / PeerLayer
  net.py           NetThread（固定 rid）
  disc.py          UDP 发现
  wire.py          消息常量
  share.py         共享面板 + 会话协调
  selftest.py      无头自测
  build_exe.py     打包脚本
  README.md        跑法、已知限制
```

## 八、构建

用 `explore/integration/.venv/Scripts/python.exe`（PySide6 6.12 + loro + websockets + PyInstaller 6.22）：

```bash
cd explore/live
../integration/.venv/Scripts/python.exe -m PyInstaller --noconfirm --onefile --windowed \
  --name "LanNote探索版" --collect-all loro --distpath . --workpath build --specpath build main.py
```

产物 `explore/live/LanNote探索版.exe`，数据在它同级的 `data/lannote.db`。

## 九、验收

- 两进程同机：A 点共享 → B 点共享 → B 自动打开 A 的笔记；双方打字收敛。
- A 点「关闭共享」→ 两边都退出共享，正文一致且各自落库。
- 面板 X/收起后共享仍在，A 还能编辑；顶栏显示「共享中」。
- A 切到别的笔记，左栏共享笔记那行仍显示 B 的头像圈；B 切走后消失。
- 空态右栏变淡、不抢焦点；左上改名生效；旧库迁移不丢笔记。
- `selftest.py` 覆盖：迁移、共享笔记插入/替换、presence 徽章计算、面板收起≠停止。

## 十、代码约束

- 遵守 `记忆.md` 第 8/10/11/12 条：短名、无文件头/分节线/模板注释、注释只写平台坑、
  不写防御性分支、自己写进库的数据不再判空。
- 不照搬 Demo 的顶栏胶囊、头像方块、名字气泡、底部房间信息。
- 不改 `app/`、`explore/integration/`。探索版只做单条共享笔记，不做多笔记同步、不做离线合并。
