#include "ym2149.h"
#include "vgmPlayer.h"


void setup() {
  // put your setup code here, to run once:
  //Serial.begin(9600);
  SetClock();
  SetBus();

  Play();
}

void loop() {
  // put your main code here, to run repeatedly:

}
