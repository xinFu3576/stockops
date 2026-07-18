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
