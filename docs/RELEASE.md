# 发布流程

## 自动化(GitHub Actions)

打 tag `vX.Y.Z` 会自动触发 `.github/workflows/release.yml`:
1. 装依赖 + 跑 pytest
2. rsync + tar 打包 `stockops-X.Y.Z.tar.gz` (~135K)
3. 建 GitHub Release + auto-generate release notes
4. 若配置了 `BREW_TAP_TOKEN` secret,自动 bump `xinFu3576/homebrew-stockops`

```bash
# 本地打 tag 触发:
git tag -a v0.7.0 -m "v0.7.0"
git push origin v0.7.0
```

## 首次配置 brew 自动 bump

在 https://github.com/xinFu3576/stockops/settings/secrets/actions 添加:

- 名: `BREW_TAP_TOKEN`
- 值: PAT (需 `repo` 权限,能写 `homebrew-stockops`)

生成 PAT:
- Settings → Developer settings → Personal access tokens → Fine-grained tokens
- Resource: `xinFu3576/homebrew-stockops`
- Permissions: `Contents: Read and write`

未配置时会跳过 bump 步骤,不阻断 Release。

## 手动流程 (fallback)

```bash
# 更新版本号
python3 -c "import json,pathlib;p=pathlib.Path('.codex-plugin/plugin.json');d=json.loads(p.read_text());d['version']='0.7.0';p.write_text(json.dumps(d,ensure_ascii=False,indent=2))"
sed -i.bak 's/VERSION ?= 0\.[0-9]\+\.0/VERSION ?= 0.7.0/' Makefile

# 测试 + 打包
make test && make pack

# 发布
gh release create v0.7.0 ../stockops-0.7.0.tar.gz --generate-notes

# bump tap (手动)
SHA=$(shasum -a 256 ../stockops-0.7.0.tar.gz | awk '{print $1}')
cd /path/to/homebrew-stockops
sed -i "s|v0.6.0/stockops-0.6.0|v0.7.0/stockops-0.7.0|; s|sha256 \"[a-f0-9]*\"|sha256 \"$SHA\"|; s|version \"0.6.0\"|version \"0.7.0\"|" Formula/stockops.rb
git commit -am "stockops 0.7.0" && git push
```

## GitHub Actions Secret 配置（v0.8.0 起 brew tap 自动 bump 依赖）

`release.yml` 在打 tag 时会自动：
1. 构建 `stockops-<ver>.tar.gz`
2. 创建 GitHub Release
3. **可选**：用 `BREW_TAP_TOKEN` push 更新 `homebrew-stockops/Formula/stockops.rb`（sha256 + version + url 三处）

### PAT 生成步骤（fine-grained token 推荐）

1. GitHub → Settings → Developer settings → **Personal access tokens** → **Fine-grained tokens** → Generate new token
2. Repository access：**Only select repositories** → 勾选 `xinFu3576/homebrew-stockops`
3. Repository permissions：
   - Contents：**Read and write**
   - Metadata：Read-only（默认）
4. Expiration：建议 90 天，到期前 renew
5. 复制 token（`github_pat_...`），只显示一次

### 加到当前仓库 secret

1. `xinFu3576/stockops` → Settings → Secrets and variables → Actions → **New repository secret**
2. Name = `BREW_TAP_TOKEN`
3. Value = 刚才复制的 PAT
4. Add secret

### 触发方式

```bash
git tag -a v0.9.0 -m "v0.9.0"
git push origin v0.9.0
# → Actions 里 release.yml 会自动跑，Release + brew tap 同时更新
```

如果 `BREW_TAP_TOKEN` 未配置，workflow 里的 brew tap 步骤会跳过（`if: env.BREW_TAP_TOKEN != ''`），Release 部分照常创建，需要手动 bump Formula。
