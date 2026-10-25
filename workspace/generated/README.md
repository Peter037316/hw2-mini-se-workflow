# TODO CLI（自动生成）

由 Mini SE Workflow 的 CodingAgent 根据 design.md 生成，零第三方依赖。

## 使用

```bash
python app.py add "买牛奶"
python app.py list
python app.py done 1
python app.py delete 1
python app.py stats
```

默认数据文件为同目录 `tasks.json`，可用 `--data` 指定。

## 测试

```bash
python -m unittest -v test_app
```
