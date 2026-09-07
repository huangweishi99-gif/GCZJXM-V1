#!/usr/bin/env python3
"""从扫描型PDF提取深圳建设工程价格信息"""
import fitz
import json
import os
import sys
from pathlib import Path
from paddleocr import PaddleOCR

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def extract_pdf_images(pdf_path, output_dir):
    """将PDF页面转换为图片"""
    os.makedirs(output_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    print(f"PDF页数: {len(doc)}")
    
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=300)
        img_path = os.path.join(output_dir, f"page_{i+1:03d}.png")
        pix.save(img_path)
        if i < 10:  # 先提取前10页进行测试
            print(f"提取第 {i+1} 页 -> {img_path}")

def ocr_images(image_dir):
    """使用OCR识别图片中的文本"""
    ocr = PaddleOCR(use_angle_cls=True, lang='ch')
    results = []
    
    for filename in sorted(os.listdir(image_dir)):
        if not filename.endswith('.png'):
            continue
        img_path = os.path.join(image_dir, filename)
        print(f"OCR识别: {img_path}")
        
        try:
            result = ocr.ocr(img_path, cls=True)
            page_text = []
            for line in result[0]:
                text = line[1][0]
                confidence = line[1][1]
                page_text.append({
                    'text': text,
                    'confidence': confidence,
                    'bbox': line[0]
                })
            results.append({
                'page': filename,
                'texts': page_text
            })
            print(f"  识别到 {len(page_text)} 行文本")
        except Exception as e:
            print(f"  识别失败: {e}")
    
    return results

def parse_price_tables(ocr_results):
    """解析OCR结果中的价格表格"""
    price_items = []
    
    for page in ocr_results:
        for item in page['texts']:
            text = item['text']
            # 简单的价格匹配模式
            # 格式可能是：材料名称 规格 单位 价格
            import re
            # 匹配价格数字（可能包含逗号）
            price_match = re.search(r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', text)
            if price_match:
                price_items.append({
                    'text': text,
                    'price': price_match.group(1),
                    'page': page['page']
                })
    
    return price_items

def main():
    pdf_path = ROOT / "清单数据资料" / "AI学习清单" / "广联达定额" / "《深圳建设工程价格信息》2023年12月造价信息.pdf"
    output_dir = ROOT / "data" / "tmp" / "pdf_images"
    ocr_output_path = ROOT / "data" / "tmp" / "ocr_results.json"
    price_output_path = ROOT / "config" / "shenzhen_price_info_2023.json"
    
    # Step 1: 提取PDF页面为图片（前10页）
    print("Step 1: 提取PDF页面为图片...")
    extract_pdf_images(pdf_path, output_dir)
    
    # Step 2: OCR识别
    print("\nStep 2: OCR识别图片...")
    ocr_results = ocr_images(output_dir)
    
    # 保存OCR原始结果
    with open(ocr_output_path, 'w', encoding='utf-8') as f:
        json.dump(ocr_results, f, ensure_ascii=False, indent=2)
    print(f"\nOCR结果已保存: {ocr_output_path}")
    
    # Step 3: 解析价格表格
    print("\nStep 3: 解析价格表格...")
    price_items = parse_price_tables(ocr_results)
    
    # 保存价格数据
    with open(price_output_path, 'w', encoding='utf-8') as f:
        json.dump(price_items, f, ensure_ascii=False, indent=2)
    print(f"价格数据已保存: {price_output_path}")
    print(f"共提取 {len(price_items)} 条价格记录")

if __name__ == '__main__':
    main()
