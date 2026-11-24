# qq-nt-chat-media-cleanup

统计 Windows 版 QQ NT 本地聊天媒体的磁盘占用：按**群**或**好友**列出空间排行，并可以只清理媒体缓存（图片 / 视频 / 表情 / 语音），**不删除聊天文字记录**。

> ⚠️ **使用范围**
>
> 本项目仅用于统计和清理**你本人电脑上**的 QQ 本地媒体缓存，不涉及登录、云端数据或他人账号。
> 读取本地数据库需要先获得解密密钥，**本项目不提供、也不分发密钥提取工具或任何 QQ 二进制文件**；如需了解，请自行查阅第三方上游项目并自行评估风险。
> 使用前请确认是否符合 QQ 用户协议及当地法律；因使用本工具导致的封号、数据损坏或丢失等后果由使用者自行承担。
> **禁止商用，禁止用于他人数据。**

## 它能做什么

QQ NT 把聊天记录存在 `nt_qq\nt_db\nt_msg.db`（加密，带 1024 字节私有头），把媒体文件按 **MD5 命名**存在 `nt_qq\nt_data\{Pic,Video,Emoji,Ptt,File}\`。

本工具在**已经拿到明文数据库**的前提下：

1. 从每条消息的 protobuf 里提取 32 位 MD5；
2. 与磁盘上的媒体文件按文件名匹配；
3. 汇总出每个群 / 每个好友的媒体占用；
4. 可选：找出「没有任何现存消息引用」的孤儿媒体（通常是已删除聊天留下的），生成删除清单；
5. 删除时只删文件、不碰数据库，并留下 path+size 日志。

## 前置条件

- Windows 10/11，Python 3.9+
- **一个已解密的 `nt_msg.db`**：本工具不负责获取密钥。数据库是 SQLCipher 加密的，需要先去掉 1024 字节私有头并用 passphrase 导出明文。相关方法的说明见 [docs/decryption.md](docs/decryption.md)，请自行判断是否适合你、并自行承担风险。
- sqlcipher CLI（脚本可自动下载）

## 快速开始

```powershell
# 1. 准备 sqlcipher CLI 及其依赖 DLL
python scripts\fetch_sqlcipher.py --dest C:\tools\sqlcipher

# 2. 统计群聊（把 --clean 指向已解密的数据库文件）
python scripts\qq_db.py usage --mode groups `
  --ntqq "D:\...\nt_qq" --db work\nt_msg.clean.db `
  --sqlcipher C:\tools\sqlcipher\bin\sqlcipher.exe `
  --group-info work\group_info.plain.db --out work\groups.json

# 3. 统计好友
python scripts\qq_db.py usage --mode friends `
  --ntqq "D:\...\nt_qq" --db work\nt_msg.clean.db `
  --sqlcipher C:\tools\sqlcipher\bin\sqlcipher.exe `
  --profile-db work\profile_info.plain.db --out work\friends.json

# 4. 找孤儿文件（可选）
python scripts\qq_db.py orphans --ntqq "D:\...\nt_qq" --db work\nt_msg.clean.db `
  --sqlcipher C:\tools\sqlcipher\bin\sqlcipher.exe --out work\orphans.csv

# 5. 先干跑，再删
python scripts\qq_db.py delete --plan work\orphans.csv --log work\deleted.csv --dry-run
python scripts\qq_db.py delete --plan work\orphans.csv --log work\deleted.csv
```

### 选择要清理的类型（`--folders`）

`usage` 和 `orphans` 都支持 `--folders`，默认统计全部五类，你可以只选其中几类：

```powershell
# 只统计图片和视频
python scripts\qq_db.py orphans --ntqq "D:\...\nt_qq" --db work\nt_msg.clean.db `
  --sqlcipher C:\tools\sqlcipher\bin\sqlcipher.exe --folders Pic,Video --out work\orphans-pic-video.csv
```

| 类型 | 内容 | 删除后的影响 |
|---|---|---|
| `Pic` | 聊天图片（原图 + 缩略图） | 聊天里变成占位，旧图基本无法重新下载 |
| `Video` | 聊天视频 | 同上，无法再播放 |
| `Ptt` | 语音消息 | 无法再回放 |
| `Emoji` | 表情 / 贴图缓存 | 对应消息里的表情显示空白 |
| `File` | 收到的文件 | 无法再打开 |

**所有类型对旧消息都只有本地这一份**：服务端只回源近期内容，历史媒体删掉一般无法恢复。所以脚本不替用户判断“删哪个安全”，只负责统计和列出清单；**删除前必须由使用者确认清单**，建议先 `--dry-run` 或先小范围试。

没有“应该删/不该删”的默认判断，删哪些类型由使用者按自己的需求决定；脚本只负责按选择统计和列出清单。

作为 DSH skill 使用：把整个目录放到 `<DSH_HOME>\skills\`（例如 `C:\Users\<你>\.dsh\skills\`），新会话即可通过 `qq-nt-chat-media-cleanup` 调用。

## 清理安全规则

1. **只删文件，不删数据库**：删 `nt_msg.db` 等于删掉全部聊天记录。
2. 清理指定群时，只删「该群引用、且其他会话都没引用」的 MD5 文件，否则别的聊天图片会裂。
3. 图片、视频、语音、表情、文件这五类对旧消息**都只有本地这一份**（服务端只回源近期内容），任何类型的删除都不可逆；脚本只负责统计和列清单，删除前必须由使用者自己确认清单，建议先 `--dry-run` 或先小范围试。
4. 删除前退出 QQ，避免文件占用；先 `--dry-run` 再执行。
5. 同一文件被多个会话引用时按会话累加会重复计数，汇总值可能略高于磁盘实际。

## 目录结构

```
SKILL.md                 # DSH skill 说明
README.md
docs/decryption.md       # 数据库解密的说明与风险提示
scripts/fetch_sqlcipher.py
scripts/qq_db.py         # usage / orphans / delete / export
```

## 路径注意

- 中间文件和导出目录请用普通路径（例如 `D:\qq-work`），**不要放在含 8.3 短名（`ADMINI~1`）的 `%TEMP%` 下**：mingw 版 sqlcipher 在部分短路径上会报 `unable to open database file (14)`。
- 路径含空格时记得用引号包住。

## 兼容性

- 设计参考版本：QQ NT 9.9.x（Windows）
- 常见参数：`cipher_page_size=4096`、`kdf_iter=4000`、`HMAC_SHA1`、`PBKDF2_HMAC_SHA512`、1024 字节私有头
- 其他版本可能不同，详见 [docs/decryption.md](docs/decryption.md)

## 本项目不提供

- 密钥提取脚本、调试器脚本、任何 QQ 客户端文件
- 对登录、云端数据、他人账号的任何访问能力
- 批量自动化抓取他人聊天记录的功能

## 免责声明

本项目按 MIT 协议“AS IS”提供，不附带任何担保。作者不对因使用本项目造成的账号处罚、数据丢失、法律纠纷或其他损失负责。请仅用于管理自己的数据，并遵守 QQ 软件许可协议及当地法律法规。

## License

MIT
