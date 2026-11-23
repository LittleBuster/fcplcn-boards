"""SRDA pin/net/part contract. Read-only; no KiCad dependency."""
SRDA_REFS = ('D1', 'D2', 'D3', 'D4', 'D6')
SRDA_DATASHEET = "https://www.littelfuse.com/assetdocs/tvs-diode-array-spa-srda05-datasheet?assetguid=5e6854f4-4140-4034-b7b2-d3793470da22"
SERIES_MPN = 'CRCW0805100RFKTAHP'
SERIES_DATASHEET = 'https://www.vishay.com/docs/20115/crcwhp.pdf'
ARRAYS = {
 'D1': ('GND', 'TVS_USB_REF', [None,None,'USB_DN','USB_DP']),
 'D2': ('GND_ISO', 'TVS_DATA14_REF_ISO', ['DATA1_ISO','DATA2_ISO','DATA3_ISO','DATA4_ISO']),
 'D3': ('GND_ISO', 'TVS_I2C_REF_ISO', ['SDA_ISO','SCL_ISO',None,None]),
 'D4': ('GND', 'TVS_LED_REF', ['LED_NET_OUT','LED_STATUS_OUT','LED_ALARM_OUT','LED_PWR_OUT']),
 'D6': ('GND_ISO', 'TVS_DATA58_REF_ISO', ['DATA5_ISO','DATA6_ISO','DATA7_ISO','DATA8_ISO'])}

def expected_arrays():
 out = {}
 for ref,(ground,ref1,signals) in ARRAYS.items():
  out[ref] = {'2':ref1,'3':ref1,'5':ground,'8':ground}
  for idx,(pin,signal) in enumerate(zip(('1','4','6','7'),signals),1):
   out[ref][pin] = signal or ground
 return out

def check_srda_contract(refs, nets, value, field, footprint, *, inventory_count=148):
 errors=[]
 raw_field=field
 def field(ref,key):
  try:return raw_field(ref,key)
  except KeyError:return ""
 def check(ok,message):
  if not ok: errors.append(message)
 check(len(refs)==inventory_count,f'Upper inventory must contain {inventory_count} components')
 check(not any(r in refs for r in ('D5','D7','D10')),'Obsolete PESD references D5/D7/D10 remain')
 check(not any('PESD' in value(r).upper() or 'PESD' in field(r,'MPN').upper() for r in refs),'PESD part remains')
 for ref,expected in expected_arrays().items():
  if ref not in refs: errors.append('Missing SRDA '+ref);continue
  check(nets(ref)==expected,ref+' SRDA pin-net map differs')
  check(value(ref)==field(ref,'MPN')=='SRDA05-4BTG',ref+' exact SRDA MPN differs')
  check(field(ref,'Manufacturer')=='Littelfuse',ref+' manufacturer differs')
  check(footprint(ref)==('RelayStack:SOIC8_SRDA_USB_Clearance' if ref=='D1' else 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm'),ref+' approved SOIC8 footprint differs')
  check(field(ref,'Datasheet')==SRDA_DATASHEET,ref+' datasheet differs')
  positive=expected['2']
  pins={(r,p) for r in refs for p,n in nets(r).items() if n==positive}
  check(pins=={(ref,'2'),(ref,'3')},ref+' REF1 is not an exclusive floating two-pin node')
  for p,n in expected.items():
   if n.startswith('unconnected-'):
    check({(r,q) for r in refs for q,k in nets(r).items() if k==n}=={(ref,p)},ref+'.'+p+' unused IO is not isolated')
 for i in range(10):
  ref='R'+str(61+i);name='DATA'+str(i+1) if i<8 else ('SDA','SCL')[i-8]
  if ref not in refs: errors.append('Missing FIELD series '+ref);continue
  check(nets(ref)=={'1':name+'_ISO','2':name+'_IC_ISO'},ref+' FIELD series pin-net map differs')
  check(value(ref)=='100R' and field(ref,'Tolerance')=='1%',ref+' value/tolerance differs')
  check(field(ref,'MPN')==SERIES_MPN and field(ref,'Manufacturer')=='Vishay',ref+' pulse-rated MPN differs')
  check(footprint(ref)=='Resistor_SMD:R_0805_2012Metric',ref+' 0805 footprint differs')
  check(field(ref,'Datasheet')==SERIES_DATASHEET,ref+' datasheet differs')
 for ref,a,b in [('U6',1,2),('U8',3,4),('U9',5,6),('U15',7,8)]:
  check(nets(ref)=={'1':'+3V3','2':f'DATA{a}_CPU','3':f'DATA{b}_CPU','4':'GND','5':'GND_ISO','6':f'DATA{b}_IC_ISO','7':f'DATA{a}_IC_ISO','8':'+5V_ISO'},ref+' isolated DATA pin map differs')
 check(nets('U7')=={'1':'+3V3','2':'ISO_SDA_CPU','3':'ISO_SCL_CPU','4':'GND','5':'GND_ISO','6':'SCL_IC_ISO','7':'SDA_IC_ISO','8':'+3V3_ISO'},'U7 isolated I2C pin map differs')
 for i,ref in enumerate(('R17','R18','R35','R36','R39','R40','R59','R60'),1):
  check(nets(ref)=={'1':'+5V_ISO','2':f'DATA{i}_IC_ISO'},ref+' pullup must be on IC side of series resistor')
 for ref,name in [('R21','SDA'),('R22','SCL')]:
  check(nets(ref)=={'1':'+3V3_ISO','2':name+'_IC_ISO'},ref+' I2C pullup must be on IC side')
 for ref,name in [('R11','USB_DN'),('R12','USB_DP')]:
  check(nets(ref)=={'1':name,'2':name+'_CPU'} and value(ref) in ('22','22R'),ref+' existing USB22R must remain')
 return errors
