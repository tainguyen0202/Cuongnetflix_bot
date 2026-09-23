import sys
import io
import zipfile
import re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def parse_item(content, fileName):
    ulpMatch = re.search(r'#\s*===\s*\[([^\]]*)\]\s*\[([^\]]*)\]\s*\[([^\]]*)\]\s*\[([A-Za-z]{2})\]\s*\[([^\]]*)\]', content)
    name = ''
    email = ''
    countryCode = ''
    planName = ''
    holdStatus = 'No'
    
    if ulpMatch:
        planName = ulpMatch.group(1).strip()
        countryCode = ulpMatch.group(4).strip().upper()
        email = ulpMatch.group(5).strip()
        
    emailMatch = re.search(r'[–-•*]?\s*Email:\s*([^\s\r\n]+)', content) or re.search(r'[\w.-]+@[\w.-]+\.[a-zA-Z]{2,}', content)
    if emailMatch and not email:
        email = emailMatch.group(1) if emailMatch.groups() else emailMatch.group(0)
        
    countryMatch = re.search(r'[–-•*]?\s*Country:\s*([A-Za-z]{2})', content) or re.search(r'\[([A-Za-z]{2})\]', fileName)
    if countryMatch and not countryCode:
        countryCode = countryMatch.group(1).upper()
        
    planMatch = re.search(r'[–-•*]?\s*Plan:\s*([^\r\n]+)', content) or re.search(r'\[([A-Za-z0-9 ]+)\]', fileName)
    if planMatch and not planName:
        planName = planMatch.group(1).strip()

    isLive = True
    deadReason = ''
    
    holdStr = (holdStatus or 'No').lower()
    if (
        holdStr == 'yes'
        or 'hold status: yes' in content.lower()
        or re.search(r'membership\s*hold|payment\s*hold|isUserOnHold\s*:\s*true|serviceEndReason\s*:\s*"?SERVICE_END_PAYMENT', content, re.I)
        or re.search(r'อัปเดตข้อมูลการชำระเงิน|cập nhật thông tin thanh toán|update your payment|update payment method', content, re.I)
    ):
        isLive = False
        deadReason = 'Hold'
    elif re.search(r'\[0\s*payments?\]', content, re.I) or re.search(r'payments?:\s*0\b', content, re.I):
        isLive = False
        deadReason = '0 payments'
    elif not planName or planName == 'Unknown':
        isLive = False
        deadReason = 'Unknown Plan'
        
    return isLive, deadReason, planName, countryCode, email

for zip_path in [r'd:\Cuồng Netflix\Netflix.zip', r'd:\Cuồng Netflix\Netflix @hydrax001.zip']:
    with zipfile.ZipFile(zip_path, 'r') as z:
        txts = [n for n in z.namelist() if n.endswith('.txt') and not n.startswith('__MACOSX')]
        live_count = 0
        die_count = 0
        reasons = {}
        for f in txts:
            content = z.read(f).decode('utf-8', errors='ignore')
            isLive, reason, plan, cc, email = parse_item(content, f)
            if isLive:
                live_count += 1
            else:
                die_count += 1
                reasons[reason] = reasons.get(reason, 0) + 1
        print(f'{zip_path}:')
        print(f'  Total TXT: {len(txts)}')
        print(f'  isLive=True: {live_count}')
        print(f'  isLive=False: {die_count}')
        print(f'  Reasons: {reasons}')
