import cv2
import requests

detector = cv2.QRCodeDetector()

cap = cv2.VideoCapture(0)

print("Show the student QR code to the camera.")
print("Press Q to quit.")

while True:

    ret, frame = cap.read()

    if not ret:
        print("Could not access camera.")
        break

    data, points, _ = detector.detectAndDecode(frame)

    if data:

        print("QR detected:", data)

        try:
            student_id = int(data)

            response = requests.post(
                "http://127.0.0.1:5000/mess/scan",
                json={"student_id": student_id}
            )

            print("Server response:")
            print(response.json())

        except ValueError:
            print("Invalid QR data.")

        break

    cv2.imshow("Mess QR Scanner", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()