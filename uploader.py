import os
import hashlib
import base64
from Yowsup.Media.uploader import MediaUploader

#Listener registrieren
#Bild Empfangen
self.signalsInterface.registerListener("image_received",self.onImageReceived)
#Bild kann auf den Whatsapp Server geladen werden
self.signalsInterface.registerListener("media_uploadRequestSuccess", self.onUploadRequestSuccess)
#Bild wurde schon hoch geladen
self.signalsInterface.registerListener("media_uploadRequestDuplicate", self.onUploadRequestDuplicate)
        

    
        
#Der letzte Schritt Bild ans Handy schicken        
def sendImage(self,url):
    #Für den Preview müsste man das Bild verkleinern, auslesen und dan base64 encodene, das war mir zu stressig, deswegen gibts bei mir nur eine kleine Himbeere als Vorschau  
    f = open("/home/pi/whatsapp/yowsup-master/src/profile.jpeg", 'r')
    stream = base64.b64encode(f.read())
      f.close()
    receiver_jid = "4915777908983@s.whatsapp.net"
    self.methodsInterface.call("message_imageSend",(receiver_jid,url,"Raspberry Pi Cam", str(os.path.getsize(self.local_path)), stream))
#Upload war erfolgreich, Bild an Handy schicken    
def onUploadSuccess(self, url):
    print("MSG send Url: "+url)
    self.sendImage(url)
    
#Wenn beim Upload ein Fehler auftritt
def onError(self):
    print("Error")
    
#Hier wird der Uploadfortschritt ausgegeben
def onProgressUpdated(self,progress):
    print(progress)

#UploadRequest erfolgreich, Bild auf den Server laden
def onUploadRequestSuccess(self, _hash, url, resumeFrom):
    #Die jid's vom sender und Empfänger, müsste man mal noch ordentlich wegkapseln 
    sender_jid = "49xxxxxxxxxxx@s.whatsapp.net"
    receiver_jid = "49xxxxxxxxxxx@s.whatsapp.net"
    MU = MediaUploader(receiver_jid,sender_jid, self.onUploadSuccess, self.onError, self.onProgressUpdated)
    MU.upload(self.local_path, url)    

#Bild wurde bereits auf den WhatsApp Server geladen nur noch das Bild ans Handy schicken         
def onUploadRequestDuplicate(self,_hash, url):
    self.sendImage(url)  
    
#Bild vom Handy empfangen    
def onImageReceived(self, messageId, jid, preview, url,  size, receiptRequested, isBroadcast):
    self.methodsInterface.call("message_send", (jid, "Image received"))
    self.methodsInterface.call("message_ack", (jid, messageId))


#Nachricht empfangen
def onMessageReceived(self, messageId, jid, messageContent, timestamp, wantsReceipt, pushName, isBroadCast):
    formattedDate = datetime.datetime.fromtimestamp(timestamp).strftime('%d-%m-%Y %H:%M')
    print("%s [%s]:%s"%(jid, formattedDate, messageContent))
    
   #Ueberpruefung das es sich um mein Handy handelt
    if jid[:13]=="49xxxxxxxxxxx":
        
        if "Image: " in messageContent:
            self.methodsInterface.call("message_send", (jid, "Upload image"))
            # Request Image upload
            self.local_path = messageContent[7:] #handy muss  eine Message in der Form [Image: /home/pi/test.jpg] (ohne eckige Klammern) schicken"
            mtype = "image"
            sha1 = hashlib.sha256()
            fp = open(self.local_path, 'rb')
            try:
                sha1.update(fp.read())
                hsh = base64.b64encode(sha1.digest())
                self.methodsInterface.call("media_requestUpload", (hsh, mtype, os.path.getsize(self.local_path)))
            finally:
                fp.close()                    
    else:
        self.methodsInterface.call("message_send", (jid, "I don't know you! Get the ***** out of my way"))
               
        
    if wantsReceipt and self.sendReceipts:
      self.methodsInterface.call("message_ack", (jid, messageId))