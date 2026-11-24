# 数据库解密说明（高风险，请先阅读）

> ⚠️ **这是本仓库里风险最高的一步，且需要第三方工具完成，本项目不提供、不分发。**
>
> - 仅可用于**你自己账号、你自己电脑上**的数据。
> - 操作涉及用调试器启动 QQ，可能造成客户端崩溃、账号被风控/冻结，甚至数据处理失败。
> - 是否进行、如何进行，请自行评估是否符合 QQ 用户协议与当地法律；一切后果由操作者承担。
> - 建议操作前备份 `nt_msg.db` 及 `nt_data` 的文件清单。

## 为什么需要解密

QQ NT 的聊天数据库 `nt_msg.db` 使用 SQLCipher 加密，并且在真正的加密数据流前还有一个 **1024 字节的私有头**。`scripts/qq_db.py` 只能读取已解密的数据库，因此需要先：

1. 取得该数据库的 passphrase；
2. 去掉 1024 字节头；
3. 用 SQLCipher 导出明文。

## 获取 passphrase（第三方，责任自负）

社区有公开工具从 QQ 进程内存中读取该 passphrase，例如 `QQBackup/qq-win-db-key`。

本仓库不包含、不打包、也不自动调用此类脚本。如果你决定使用，请自行克隆并阅读其源码与风险说明：

```powershell
git clone https://github.com/QQBackup/qq-win-db-key
```

通常流程是：完全退出 QQ → 运行其 Windows/NTQQ 脚本 → 脚本用调试器启动 QQ → 在 `sqlite3_key_v2` 处抓取 16 位字符串。

注意：

- 抓到的可能是 `login.db` 而非 `nt_msg.db` 的密钥，不同次运行结果可能不同；
- 字符串形如 `#8xxxxxxxxxxx@uJ`，区分大小写，长度 16；
- 任何异常都可能导致 QQ 需要重新登录。

## 去掉 1024 字节头并导出明文

拿到 passphrase 后，可用本仓库的脚本：

```powershell
python scripts\qq_db.py export `
  --src   "D:\...\nt_qq\nt_db\nt_msg.db" `
  --clean work\nt_msg.clean.db `
  --out   work\nt_msg.plain.db `
  --sqlcipher C:\tools\sqlcipher\bin\sqlcipher.exe `
  --key "<passphrase>"
```

`--clean` 是中间文件（原库大小），`--out` 是明文库；确认成功后中间文件可以删除。

## 参数与排错

| 参数 | 常见值 |
|---|---|
| 私有头 | 1024 字节 |
| `cipher_page_size` | 4096（必须在 `key` 之前设置） |
| `kdf_iter` | 4000 |
| `cipher_hmac_algorithm` | `HMAC_SHA1`（失败再试 `HMAC_SHA256` / `HMAC_SHA512`） |
| `cipher_kdf_algorithm` | `PBKDF2_HMAC_SHA512` |

- `file is not a database`：密钥错误，或 HMAC/KDF 参数不匹配。先用 `SELECT count(*) FROM sqlite_master` 验证。
- `database disk image is malformed`：数据页损坏或版本不匹配。按 `40027` 逐群查询（本仓库脚本的做法）比全表扫描更稳。
- `unable to open database file (14)`：通常是路径问题，换一个普通路径（避免 `%TEMP%` 的 8.3 短名）。

## 提醒

- 明文数据库包含全部聊天内容，请注意存放位置与删除；
- 不要把数据库、密钥、聊天内容提交到 Git 或分享给他人；
- 本项目其余脚本只做媒体统计与文件删除，不会修改数据库内容。
