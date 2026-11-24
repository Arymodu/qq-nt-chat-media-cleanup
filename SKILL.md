---
name: qq-nt-chat-media-cleanup
description: "统计 Windows 版 QQ NT（9.9.x）本地聊天媒体的磁盘占用，按群/好友列出空间排行，并安全清理指定会话的图片/视频/表情/语音（不删聊天文字）。需要先有一个已解密的本地数据库；解密步骤与风险见 docs/decryption.md。"
---

# QQ NT 聊天占用审计与清理

> ⚠️ **使用边界**：仅用于**本人电脑、本人账号**的本地媒体统计与清理；不涉及登录、云端或他人数据。读取加密数据库属于高风险步骤，本项目不提供、不分发包密钥的工具，是否使用请自行判断并承担后果。禁止商用。

适用：Windows 版 QQ NT 9.9.x。目标：看清每个群、每个好友占了多少磁盘，并只清理媒体文件（图片/视频/表情/语音），**不改动聊天文字**。

## 原理

- 聊天记录在 `nt_qq\nt_db\nt_msg.db`，加密，前面有 1024 字节私有头。
- 媒体在 `nt_qq\nt_data\{Pic,Video,Emoji,Ptt,File}\`，文件名基本是 32 位 MD5（缩略图带 `_0` 后缀）。
- 每条消息的 protobuf（`group_msg_table.40800` / `c2c_msg_table.40800`）里带着图片/文件的 MD5。
- 因此「某会话占多少」= 该会话消息中出现过的 MD5 → 对应磁盘文件大小之和。

## 前置条件

- Windows + Python 3.9+，已登录过的 QQ NT
- **一个已解密的 `nt_msg.db`**（去掉 1024 字节头 + 导出明文）。如何解密不在本 skill 的自动流程内，详见 `docs/decryption.md`，请自行评估风险。
- sqlcipher CLI（可用脚本自动下载）

## 步骤

### 0. 准备 sqlcipher CLI

```powershell
python scripts\fetch_sqlcipher.py --dest C:\tools\sqlcipher
```

失败时可设 `HTTPS_PROXY` 重试；脚本里的包列表可按需更新。

### 1. 准备已解密的数据库

`--db` 指向解密后的 `nt_msg.clean.db`。解密本身需要 passphrase，属于高风险、依赖第三方工具的操作，见 `docs/decryption.md`；不完成这一步，后面的统计无法进行。

### 2. 统计

群聊：

```powershell
python scripts\qq_db.py usage --mode groups `
  --ntqq "D:\...\nt_qq" --db work\nt_msg.clean.db `
  --sqlcipher C:\tools\sqlcipher\bin\sqlcipher.exe `
  --group-info work\group_info.plain.db --out work\groups.json
```

好友：

```powershell
python scripts\qq_db.py usage --mode friends `
  --ntqq "D:\...\nt_qq" --db work\nt_msg.clean.db `
  --sqlcipher C:\tools\sqlcipher\bin\sqlcipher.exe `
  --profile-db work\profile_info.plain.db --out work\friends.json
```

`group_info.db` / `profile_info.db` 用 `export` 子命令按同样方式导出（参数相同）；不提供时只会缺群名/昵称。

可选 `--folders Pic,Video` 只统计指定类型（默认 `Pic,Video,Emoji,Ptt,File` 全部）；清理哪些类型由你选择。

### 3. 孤儿文件（可选）

```powershell
python scripts\qq_db.py orphans --ntqq "D:\...\nt_qq" --db work\nt_msg.clean.db `
  --sqlcipher C:\tools\sqlcipher\bin\sqlcipher.exe --out work\orphans.csv
```

孤儿 = 没有任何现存消息引用的媒体（通常来自已删除的聊天记录）。删除前先抽查 CSV。

### 4. 删除

```powershell
python scripts\qq_db.py delete --plan work\orphans.csv --log work\deleted.csv --dry-run
python scripts\qq_db.py delete --plan work\orphans.csv --log work\deleted.csv
```

## 参数与排错

| 项 | 值 |
|---|---|
| 私有头 | 1024 字节 |
| `cipher_page_size` | 4096（必须在 `key` 之前） |
| `kdf_iter` | 4000 |
| `cipher_hmac_algorithm` | `HMAC_SHA1`（失败再试 SHA256 / SHA512） |
| `cipher_kdf_algorithm` | `PBKDF2_HMAC_SHA512` |

- `file is not a database`：密钥或 HMAC/KDF 参数不对，先 `SELECT count(*) FROM sqlite_master` 验证。
- `database disk image is malformed`：按 `40027` 逐群查询（本 skill 做法）比全表扫更稳。
- `unable to open database file (14)`：路径问题，避免 `%TEMP%` 的 8.3 短名。

## 删除安全规则

1. **只删文件，不删数据库**：删 `nt_msg.db` 等于删掉全部聊天记录。
2. 清理指定群时，只删「该群引用、且其他会话都没引用」的 MD5 文件。
3. 五种类型对旧消息都只有本地副本（服务端只回源近期内容），**任何类型的删除都不可逆**；脚本只负责列清单，必须先由使用者确认清单（建议 `--dry-run` 或先小范围试）再执行。
4. 删除前退出 QQ；先 `--dry-run` 再执行。
5. 共享文件在多个会话间会重复计数，汇总可能略高于磁盘实际。

## 本项目不提供

- 密钥提取脚本、调试器脚本、任何 QQ 客户端文件
- 访问登录、云端数据或他人账号的能力
