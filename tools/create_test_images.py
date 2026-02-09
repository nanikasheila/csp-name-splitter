from PIL import Image
import random

# test_envディレクトリに複数のテスト画像を生成
for i in range(1, 4):
    # 16x16のランダム画像を作成
    img = Image.new('RGB', (16, 16))
    pixels = []
    for y in range(16):
        for x in range(16):
            pixels.append((random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))
    img.putdata(pixels)
    img.save(f'test_env/sample{i}.png')
    print(f'Created test_env/sample{i}.png')
