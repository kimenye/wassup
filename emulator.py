from ongair import Ongair, OngairStack
from yowsup.layers.auth                        import YowAuthenticationProtocolLayer
from yowsup.layers.protocol_messages           import YowMessagesProtocolLayer
from yowsup.layers.protocol_receipts           import YowReceiptProtocolLayer
from yowsup.layers.protocol_acks               import YowAckProtocolLayer
from yowsup.layers.network                     import YowNetworkLayer
from yowsup.layers.coder                       import YowCoderLayer
from yowsup.layers.protocol_media              import YowMediaProtocolLayer
from yowsup.layers.protocol_iq                 import YowIqProtocolLayer

from yowsup.stacks import YowStack
from yowsup.common import YowConstants
from yowsup.layers import YowLayerEvent
from yowsup.stacks import YowStack, YOWSUP_CORE_LAYERS
from yowsup import env


CREDENTIALS = ("254716085380", "N011FOHQ460iMpWDDx6Ou+j1lFA=") # replace with your phone and password

if __name__==  "__main__":
  OngairLayer = Ongair("254716085380")
  layers = (
      OngairLayer,
      (YowAuthenticationProtocolLayer, YowMessagesProtocolLayer, YowReceiptProtocolLayer, YowAckProtocolLayer, YowMediaProtocolLayer, YowIqProtocolLayer)
  ) + YOWSUP_CORE_LAYERS

  stack = OngairStack(layers)
  stack.setProp(YowAuthenticationProtocolLayer.PROP_CREDENTIALS, CREDENTIALS)         #setting credentials
  stack.setProp(YowNetworkLayer.PROP_ENDPOINT, YowConstants.ENDPOINTS[0])    #whatsapp server address
  stack.setProp(YowCoderLayer.PROP_DOMAIN, YowConstants.DOMAIN)              
  stack.setProp(YowCoderLayer.PROP_RESOURCE, env.CURRENT_ENV.getResource())          #info about us as WhatsApp client

  stack.broadcastEvent(YowLayerEvent(YowNetworkLayer.EVENT_STATE_CONNECT))   #sending the connect signal

  stack.loop() #this is the program mainloop