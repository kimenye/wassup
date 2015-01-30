from yowsup.layers.interface                           import YowInterfaceLayer, ProtocolEntityCallback
from yowsup.layers.protocol_messages.protocolentities  import TextMessageProtocolEntity
from yowsup.layers.protocol_receipts.protocolentities  import OutgoingReceiptProtocolEntity
from yowsup.layers.protocol_acks.protocolentities      import OutgoingAckProtocolEntity
from yowsup.layers.protocol_iq.protocolentities        import PingIqProtocolEntity
from yowsup.layers.protocol_media.protocolentities     import RequestUploadIqProtocolEntity, ResultRequestUploadIqProtocolEntity, ImageDownloadableMediaMessageProtocolEntity
from yowsup.layers.protocol_media.mediauploader import MediaUploader
from yowsup.stacks import YowStack

from models import Account, Message, Job
from util import get_phone_number, error_message, utc_to_local, setup_logging
import asyncore, requests

class Ongair(YowInterfaceLayer):

  def __init__(self, phone_number):
    super(Ongair, self).__init__()
    self.phone_number = phone_number

    logger = setup_logging(phone_number, "development")
    logger.info("Starting layer for : %s" %phone_number)
    self.logger = logger


  @ProtocolEntityCallback("message")
  def onMessage(self, messageProtocolEntity):
    receipt = OutgoingReceiptProtocolEntity(messageProtocolEntity.getId(), messageProtocolEntity.getFrom())
    
    # outgoingMessageProtocolEntity = TextMessageProtocolEntity(
    #   messageProtocolEntity.getBody(),
    #   to = messageProtocolEntity.getFrom())
    text = messageProtocolEntity.getBody()
    message_id = messageProtocolEntity.getId().split("-")[0]

    api_url =   "http://localhost:9292/api/pictures/share?recipient=%s&id=%s" %(text, message_id)
    self.logger.info("Going to generate url for %s" %api_url)

    file_path = "tmp/%s.png" %message_id
    img = open(file_path, 'wb')
    img.write(requests.get(api_url).content)
    img.close()

    to = messageProtocolEntity.getFrom()
    # self.logger.info("To %s" %to)
    # file_path = "/Users/trevor/Projects/whatsapp/tmp/1422609541.png"

    self.requestImageUpload(to, file_path)

    self.toLower(receipt)
    # self.toLower(outgoingMessageProtocolEntity)

  @ProtocolEntityCallback("receipt")
  def onReceipt(self, entity):
    ack = OutgoingAckProtocolEntity(entity.getId(), "receipt", "delivery")
    self.toLower(ack)

  def requestImageUpload(self, to, path):
    self.logger.info("Requesting image upload... %s" %path)

    entity = RequestUploadIqProtocolEntity(RequestUploadIqProtocolEntity.MEDIA_TYPE_IMAGE, filePath=path)
    successFn = lambda successEntity, originalEntity: self.onRequestUploadResult(to, path, successEntity, originalEntity)
    errorFn = lambda errorEntity, originalEntity: self.onRequestUploadError(to, path, errorEntity, originalEntity)

    self._sendIq(entity, successFn, errorFn)
    self.logger.info("Sent IQ")
  
  def onRequestUploadResult(self, jid, filePath, resultRequestUploadIqProtocolEntity, requestUploadIqProtocolEntity):
    self.logger.info("Got an image upload request...")
    if resultRequestUploadIqProtocolEntity.isDuplicate():
      self.doSendImage(filePath, resultRequestUploadIqProtocolEntity.getUrl(), jid, resultRequestUploadIqProtocolEntity.getIp())
    else:
      mediaUploader = MediaUploader(jid, self.getOwnJid(), filePath,
        resultRequestUploadIqProtocolEntity.getUrl(),
        resultRequestUploadIqProtocolEntity.getResumeOffset(),
        self.onUploadSuccess, self.onUploadError, self.onUploadProgress, async=False)

      mediaUploader.start()

  def onRequestUploadError(self, errorRequestUploadIqProtocolEntity, requestUploadIqProtocolEntity):
    self.logger.info("Error requesting upload url")

  def onUploadSuccess(self, filePath, jid, url):
    self.doSendImage(filePath, url, jid)

  def onUploadError(self, filePath, jid, url):
    self.logger.error("Upload file %s to %s for %s failed!" % (filePath, url, jid))

  def onUploadProgress(self, filePath, jid, url, progress):
    self.logger.info("%s => %s, %d%% \r" % (filePath, jid, progress))

  def doSendImage(self, filePath, url, to, ip = None):
    self.logger.info("Sending image...")
    entity = ImageDownloadableMediaMessageProtocolEntity.fromFilePath(filePath, url, ip, to)
    self.toLower(entity)

# subclassing Stack 
class OngairStack(YowStack):

  def __init__(self, layers):
    super(OngairStack, self).__init__(layers)


  def loop(self, *args, **kwargs):
    if "discrete" in kwargs:
      discreteVal = kwargs["discrete"]
      del kwargs["discrete"]
      while True:
          asyncore.loop(*args, **kwargs)
          time.sleep(discreteVal)
          try:
              callback = self.__class__.__detachedQueue.get(False) #doesn't block
              callback()
          except Queue.Empty:
              pass
    else:
      print "Asyncore loop"
      # asyncore.loop(*args, **kwargs)
      asyncore.loop(timeout=1)
      print "End of loop"
