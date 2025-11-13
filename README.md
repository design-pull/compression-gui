### README.md

# compression-gui

ローカルで画像（PNG / JPEG）を一括圧縮するシンプルなGUIツールです。Pillow を基本に、pngquant がある環境ではより高率な PNG 圧縮を行います。PyInstaller による onefile Windows ビルドと、GitHub Actions での自動ビルド／Release 作成フローを含みます。

---

### ハイライト
- GUI: ttkbootstrap + Tkinter  
- 圧縮エンジン: Pillow（常時）; pngquant（tools/pngquant.exe がある場合に使用）  
- 配布: onefile Windows EXE を GitHub Releases で配布（CI 自動化済み）  
- 再現性: CI は tools/pngquant.exe をリポジトリに置く前提でビルド可能

---

### ダウンロードと検証（Windows 利用者向け）
1. Releases ページへアクセス: https://github.com/design-pull/compression-gui/releases  
2. 配布アセット（例: app-windows-v1.0.0.zip）をダウンロード  
3. SHA256 を検証（PowerShell）:
```powershell
Get-FileHash .\app-windows-v1.0.0.zip -Algorithm SHA256 | Format-List
```
4. ZIP を展開し、dist\app.exe を実行

> セキュリティ注意: 署名が付いていないビルドもあります。より強い信頼性が必要なら署名済みリリースを待つか、ソースと CI ログを確認してください。

---

### 動作要件（開発者向け）
- Windows 10 / 11（実行確認）  
- Python 3.12（開発推奨）  
- 仮想環境（.venv）推奨  
- 依存は requirements.txt に記載

requirements.txt の例:
```
Pillow>=10.0.0
ttkbootstrap>=1.6.0
```

pngquant をローカルで使う場合は tools/pngquant.exe を配置してください（オプション）。

---

### ソースから起動する（開発用クイックスタート）
```powershell
git clone https://github.com/design-pull/compression-gui.git
cd compression-gui
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

---

### ローカルでのビルド（onefile, Windows）
```powershell
# 仮想環境を有効化した状態で
python -m pip install pyinstaller==6.16.0
pyinstaller --onefile --noconsole --icon=img\icon.ico --add-data "img;img" --add-data "tools;tools" app.py
# 出力: dist\app.exe
```

デバッグ用にコンソールを有効にする場合:
```powershell
pyinstaller --onefile --console --icon=img\icon.ico --add-data "img;img" --add-data "tools;tools" app.py
.\dist\app.exe
```

---

### CI とリリース（自動化）
- .github/workflows/build-release-windows.yml によって、タグ（例 v1.0.0）を push すると Windows ビルドが走り、Release ドラフトに ZIP と SHA256 が添付されます。  
- reproducible を重視するなら tools/pngquant.exe をリポジトリにピン留めしておくことを推奨します（ワークフローはその前提で作成済み）。

タグ例:
```bash
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

---

### 使い方メモ
- 出力フォルダは自動作成されます。  
- ドライラン機能で想定削減量を確認できます。  
- 実行ログや例外はプロジェクトルートの app_run.log に出力されます（UTF‑8）。不具合報告の際は最後の200行を添付してください。

---

### トラブルシューティング（よくある問題）
- ModuleNotFoundError（例: ttkbootstrap）: ビルドに使う Python 環境で `pip install -r requirements.txt` を実行し、同じ環境で `python -m PyInstaller ...` を使って再ビルドしてください。  
- PermissionError（dist\app.exe の削除失敗）: 実行中の app プロセスを停止（Get-Process -Name app | Stop-Process -Force）するか PC を再起動してから再ビルドしてください。  
- pngquant が使われない: tools/pngquant.exe が同梱されているか確認。CI で同梱する場合は workflow が該当ファイルを検出できるようにしてください。  
- ログが文字化けする場合: PowerShell で UTF‑8 指定して表示（Get-Content .\app_run.log -Encoding UTF8 -Tail 200）。

---

### 配布アセット（推奨構成）
- app-windows-<tag>.zip （dist\app.exe を含む）  
- SHA256SUM-<tag>.txt  
- README.md（このファイル）  
- CHANGELOG.md（リリース情報）  
- LICENSE.txt

---

### コントリビュート
- Fork → ブランチ → Pull Request のフローでお願いします。  
- 新しい依存を追加する場合は requirements.txt を更新してください。  
- 大きなバイナリは Git LFS を検討してください。

---

### ライセンス
LICENSE ファイルをプロジェクトルートに置いてください（未指定の場合はまずライセンスを決めてください）。

---

### サポート
不具合報告は GitHub Issues にて。報告時は次を添えてください：
- 使用 OS と Python バージョン  
- 該当リリースタグ  
- app_run.log の最後 200 行（UTF‑8）  
- 再現手順