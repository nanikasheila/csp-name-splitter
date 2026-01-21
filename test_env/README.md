# テスト用環境

このディレクトリには、CLIの動作確認に使う最小構成のデータが入っています。

## 構成

- `sample.ppm`: 16x16のチェッカーボード画像（テスト用画像）
- `test_config.yaml`: テスト用設定

## 使い方

1. 画像をPSDに変換（ImageMagickが必要）

```bash
convert sample.ppm sample.psd
```

2. CLIで実行

```bash
python -m name_splitter.app.cli sample.psd --config test_config.yaml --out-dir output
```

3. 生成される `output/plan.json` を確認

## 依存なしのスモークテスト

PyYAMLやpsd-toolsが未導入の場合は、以下のスモークテストで
グリッド計算と `plan.json` 生成だけを確認できます。

```bash
PYTHONPATH=.. python ../tools/run_smoke_test.py
```
