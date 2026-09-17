import qrcode

student_id = input("Enter student ID: ")

img = qrcode.make(student_id)

filename = f"student_{student_id}_qr.png"
img.save(filename)

print(f"QR code created: {filename}")