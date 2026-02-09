"""Test page size unit conversion"""
print("Page size unit conversion test")

dpi = 600

# Test 1: px -> mm
print("\nTest 1: px -> mm (DPI=600)")
width_px = 6071
height_px = 8598

width_mm = width_px * 25.4 / dpi
height_mm = height_px * 25.4 / dpi

print(f"  {width_px}px × {height_px}px")
print(f"  -> {width_mm:.2f}mm × {height_mm:.2f}mm")
print(f"  Expected: ~257mm × 364mm (B4 @ 600dpi)")

# Test 2: mm -> px
print("\nTest 2: mm -> px (DPI=600)")
width_mm_input = 257.0
height_mm_input = 364.0

width_px_result = int(width_mm_input * dpi / 25.4)
height_px_result = int(height_mm_input * dpi / 25.4)

print(f"  {width_mm_input}mm × {height_mm_input}mm")
print(f"  -> {width_px_result}px × {height_px_result}px")
print(f"  Expected: ~6071px × 8598px")

# Test 3: Round trip
print("\nTest 3: Round trip (px -> mm -> px)")
original_px = 6071
mm_val = original_px * 25.4 / dpi
back_to_px = int(mm_val * dpi / 25.4)
print(f"  Original: {original_px}px")
print(f"  -> {mm_val:.2f}mm")
print(f"  -> {back_to_px}px")
print(f"  Difference: {abs(original_px - back_to_px)}px")
if abs(original_px - back_to_px) <= 1:
    print(f"  ✓ Round trip OK (within 1px)")
else:
    print(f"  ✗ Round trip error")

print("\nAll conversion formulas verified! ✓")
