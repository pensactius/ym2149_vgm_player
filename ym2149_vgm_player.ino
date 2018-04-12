#include "ym2149.h"

// Define here USB baud rate to receive song data
#define BAUD 57600

unsigned char cmd, addr, data;

void setup() {
  
  Serial.begin(BAUD);
  while (!Serial) {
    ;
  }
  
  SetClock();
  SetBus();

  ClearRegisters();

  Serial.println("Ready");  
}

void loop() {
  while (!(Serial.available() >0)) {}
  if (Serial.available() > 0)
    cmd = Serial.read();

    if (cmd == 0xA0) {
    
      while (!(Serial.available() >0)) {}
      if (Serial.available() > 0)
        addr = Serial.read();
    
      while (!(Serial.available() >0)) {}
      if (Serial.available() > 0)
        data = Serial.read();      
      
      YMWriteData(addr, data);
    }

    else if (cmd == 0xFF) {
      ClearRegisters();
    }
}

void ClearRegisters(void)
{
  for (int i=0; i<14; i++)
  {
    YMWriteData(i, 0);
  }
}
