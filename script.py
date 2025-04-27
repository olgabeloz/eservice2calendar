import time
import requests
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError
from datetime import datetime
from datetime import timedelta
from google.auth import impersonated_credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build


SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_eservice_data(group_id):
    url = f"https://eservice.omsu.ru/schedule/backend/schedule/group/{group_id}" 
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data
    else:
        print(f"Ошибка при получении данных с Eservice для группы {group_id}. Код ошибки: {response.status_code}")
        return None

def authenticate_google():
    SERVICE_ACCOUNT_FILE = 'credentials.json'
    
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)

    service = build('calendar', 'v3', credentials=creds)
    
    return service


TIME_SLOTS = {
    1: "08:45:00",
    2: "10:30:00",
    3: "12:45:00",
    4: "14:30:00",
    5: "16:15:00",
    6: "17:50:00",
    7: "18:00:00",
}

def get_time_range(date_str, time_slot):
    date_obj = datetime.strptime(date_str, "%d.%m.%Y")
    start_time_str = TIME_SLOTS.get(time_slot, "08:45:00")
    start_dt = datetime.strptime(f"{date_obj.strftime('%Y-%m-%d')}T{start_time_str}", "%Y-%m-%dT%H:%M:%S")
    end_dt = start_dt + timedelta(minutes=95)  # пара длится 1 час 35 минут
    return start_dt.isoformat(), end_dt.isoformat()

def delete_old_events(service, date, calendar_id):
    try:
        date_obj = datetime.strptime(date, "%d.%m.%Y")
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        if date_obj < today:
            print(f"Пропуск удаления событий за прошедшую дату: {date}")
            return

        time_min = date_obj.strftime('%Y-%m-%d') + "T00:00:00Z"
        time_max = date_obj.strftime('%Y-%m-%d') + "T23:59:59Z"

        print(f"Удаление событий с {time_min} по {time_max}")

        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        if not events:
            print(f"Нет событий для удаления на дату: {date}")
        else:
            for event in events: 
                service.events().delete(calendarId=calendar_id, eventId=event['id']).execute()
                print(f"Удалено событие: {event['summary']}")
                time.sleep(2)

    except HttpError as error:
        print(f"Ошибка при удалении событий: {error}")


def add_new_events(service, data, calendar_id):
    color_mapping = {
        "Производственная практика": "8",  # Серый
        "Прак": "11",                      # Красный
        "Лек": "9",                        # Синий
        "Лаб": "10",                       # Зеленый
    }
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    for lesson in data['data']:
        lesson_date = datetime.strptime(lesson['day'], "%d.%m.%Y")
        if lesson_date < today:
            print(f"Пропуск добавления событий за прошедшую дату: {lesson['day']}")
            continue

        for lesson_info in lesson['lessons']:
            start_iso, end_iso = get_time_range(lesson_info['day'], lesson_info['time'])
            
            description = f"Преподаватель: {lesson_info['teacher']}\n"  
            if lesson_info.get('subgroupName'):
                description += f"\nПодгруппа: {lesson_info['subgroupName']}"
            
            event = {
                'summary': lesson_info['lesson'],
                'location': lesson_info['auditCorps'],
                'description': description,
                'start': {
                    'dateTime': start_iso,
                    'timeZone': 'Asia/Omsk',
                },
                'end': {
                    'dateTime': end_iso,
                    'timeZone': 'Asia/Omsk',
                },
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': 10}
                    ],
                },
            }
            type_work = lesson_info.get('type_work')
            if type_work in color_mapping:
                event['colorId'] = color_mapping[type_work]
            
            try:
                created_event = service.events().insert(calendarId=calendar_id, body=event).execute()
                print(f"Добавлено событие: {created_event['summary']}")
                time.sleep(2)
            except HttpError as error:
                print(f"Ошибка при добавлении события: {error}")
                print("DEBUG BODY:", event)


def main():
    group_ids = [5008, 10986, 10984, 10987]
    calendar_ids = [
        '4d57800b0b4d56e33065dd9754313b51e4d1d953dbadfca7f78a30f6cb4c5b57@group.calendar.google.com',  # Омский
        '63886184f0ba91e706d3fc8d4d6705594f283cb3815b5824df24bb988e01e306@group.calendar.google.com',  # Календарь для группы 10986
        '9fe497a42c82d6a0f8a864d13022f1f53dd4540a896558dde7da515fe3e03df7@group.calendar.google.com',  # Календарь для группы 10984
        'e34a1dc253ba9d094cedc96fee5fa55eb37bc02dcdcec288977dc72d1f021b9c@group.calendar.google.com'   # Календарь для группы 10987
    ]
    
    for group_id, calendar_id in zip(group_ids, calendar_ids):
        print(f"Обработка группы {group_id} с календарем {calendar_id}...")
        
        data = get_eservice_data(group_id)
        if not data:
            print(f"Не удалось получить данные с Eservice для группы {group_id}.")
            continue

        service = authenticate_google()

        for lesson in data['data']:
            delete_old_events(service, lesson['day'], calendar_id)

        add_new_events(service, data, calendar_id)

if __name__ == '__main__':
    main()
