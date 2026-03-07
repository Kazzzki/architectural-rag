import os
from pypdf import PdfWriter

writer = PdfWriter()
writer.add_blank_page(width=100, height=100)
with open("test_real.pdf", "wb") as f_out:
    writer.write(f_out)
print("Created test_real.pdf")
