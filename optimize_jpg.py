#!/usr/bin/env python3
import os
import sys
import argparse
from PIL import Image

def get_size_format(b, factor=1024, suffix="B"):
    """
    Форматирует размер байт в удобочитаемый вид (например: 1.20MB)
    """
    for unit in ["", "KB", "MB", "GB", "TB"]:
        if b < factor:
            return f"{b:.2f} {unit}"
        b /= factor
    return f"{b:.2f} PB"

def optimize_image(input_path, output_path, quality, max_size, keep_exif):
    """
    Оптимизирует одно изображение JPG/JPEG.
    """
    try:
        # Проверяем расширение
        ext = os.path.splitext(input_path)[1].lower()
        if ext not in ['.jpg', '.jpeg']:
            print(f"Пропуск (не JPEG): {input_path}")
            return False, 0, 0

        original_size = os.path.getsize(input_path)
        
        with Image.open(input_path) as img:
            # Конвертируем изображения с альфа-каналом (RGBA/LA) или палитрой в RGB
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                bg = Image.new('RGB', img.size, (255, 255, 255))
                mask = img.split()[3] if img.mode == 'RGBA' else img.convert('RGBA').split()[3]
                bg.paste(img, mask=mask)
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Изменение размера, если изображение превышает max_size по ширине или высоте
            if max_size:
                width, height = img.size
                if width > max_size or height > max_size:
                    if width > height:
                        new_width = max_size
                        new_height = int((max_size / width) * height)
                    else:
                        new_height = max_size
                        new_width = int((max_size / height) * width)
                    
                    # Использование Resampling.LANCZOS для качественного сжатия
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            save_kwargs = {
                'quality': quality,
                'optimize': True,
                'progressive': True
            }
            
            # Сохранение/удаление метаданных EXIF (геолокация, модель камеры и т.д.)
            if keep_exif:
                exif = img.info.get('exif')
                if exif:
                    save_kwargs['exif'] = exif
            
            # Временное сохранение во временный файл, если заменяем на месте
            temp_path = output_path + ".tmp" if input_path == output_path else output_path
            
            img.save(temp_path, 'JPEG', **save_kwargs)
            
            if input_path == output_path:
                if os.path.exists(output_path):
                    os.remove(output_path)
                os.rename(temp_path, output_path)
        
        optimized_size = os.path.getsize(output_path)
        saved = original_size - optimized_size
        percent = (saved / original_size) * 100 if original_size > 0 else 0
        
        print(f"Оптимизирован: {os.path.basename(input_path)}")
        print(f"  Размер: {get_size_format(original_size)} -> {get_size_format(optimized_size)} (Сжато на: {percent:.1f}%)")
        
        return True, original_size, optimized_size
    except Exception as e:
        print(f"Ошибка при обработке {input_path}: {e}")
        return False, 0, 0

def main():
    parser = argparse.ArgumentParser(description="Скрипт на Python для пакетной оптимизации и сжатия изображений JPG/JPEG.")
    parser.add_argument("input", help="Путь к файлу JPEG или папке с файлами")
    parser.add_argument("-o", "--output", help="Путь для сохранения результата (если не указан, файлы заменяются на месте)")
    parser.add_argument("-q", "--quality", type=int, default=85, help="Качество JPEG от 1 до 95 (по умолчанию: 85)")
    parser.add_argument("-m", "--max-size", type=int, default=2000, help="Максимальный размер стороны (ширина/высота) в пикселях. Более крупные фото будут пропорционально уменьшены. 0 — отключить ресайз (по умолчанию: 2000)")
    parser.add_argument("--keep-exif", action="store_true", help="Сохранить метаданные EXIF (GPS, модель камеры и т.д.). По умолчанию метаданные удаляются для экономии места.")
    parser.add_argument("-r", "--recursive", action="store_true", help="Рекурсивный поиск файлов JPEG в подпапках")

    args = parser.parse_args()

    input_path = os.path.abspath(args.input)
    if not os.path.exists(input_path):
        print(f"Ошибка: Путь '{args.input}' не существует.")
        sys.exit(1)

    targets = []
    if os.path.isfile(input_path):
        targets.append(input_path)
        is_dir_mode = False
    else:
        is_dir_mode = True
        if args.recursive:
            for root, _, files in os.walk(input_path):
                for f in files:
                    if f.lower().endswith(('.jpg', '.jpeg')):
                        targets.append(os.path.join(root, f))
        else:
            for f in os.listdir(input_path):
                if f.lower().endswith(('.jpg', '.jpeg')):
                    targets.append(os.path.join(input_path, f))

    if not targets:
        print("Файлы JPEG для оптимизации не найдены.")
        sys.exit(0)

    print(f"Найдено файлов для оптимизации: {len(targets)}")
    
    total_original = 0
    total_optimized = 0
    success_count = 0

    for file_path in targets:
        if args.output:
            out_base = os.path.abspath(args.output)
            if is_dir_mode:
                if not os.path.exists(out_base):
                    os.makedirs(out_base, exist_ok=True)
                file_rel = os.path.relpath(file_path, input_path)
                out_path = os.path.join(out_base, file_rel)
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
            else:
                if os.path.isdir(out_base) or args.output.endswith('/') or args.output.endswith('\\'):
                    os.makedirs(out_base, exist_ok=True)
                    out_path = os.path.join(out_base, os.path.basename(file_path))
                else:
                    out_path = out_base
        else:
            out_path = file_path

        success, orig, opt = optimize_image(
            file_path, 
            out_path, 
            quality=args.quality, 
            max_size=args.max_size if args.max_size > 0 else None, 
            keep_exif=args.keep_exif
        )
        if success:
            success_count += 1
            total_original += orig
            total_optimized += opt

    if success_count > 0:
        total_saved = total_original - total_optimized
        total_percent = (total_saved / total_original) * 100 if total_original > 0 else 0
        print("\n=== Итоги оптимизации ===")
        print(f"Успешно обработано: {success_count} из {len(targets)} файлов")
        print(f"Общий исходный размер: {get_size_format(total_original)}")
        print(f"Общий оптимизированный размер: {get_size_format(total_optimized)}")
        print(f"Сэкономлено места: {get_size_format(total_saved)} (-{total_percent:.1f}%)")
    else:
        print("\nНе удалось оптимизировать ни один файл.")

if __name__ == "__main__":
    main()
