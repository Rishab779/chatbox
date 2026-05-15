import boto3
from botocore.exceptions import ClientError
import os
import time
from decimal import Decimal
from dotenv import load_dotenv
from boto3.dynamodb.conditions import Key

load_dotenv()

# DynamoDB Configuration
# Boto3 will automatically use AWS credentials from environment variables, 
# AWS CLI config, or EC2 instance roles.
dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_DEFAULT_REGION', 'ap-south-1'))
TABLE_NAME = 'ChatboxUsers'

def get_table():
    try:
        table = dynamodb.Table(TABLE_NAME)
        table.load()
        return table
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            # Create table if it doesn't exist
            table = dynamodb.create_table(
                TableName=TABLE_NAME,
                KeySchema=[
                    {'AttributeName': 'username', 'KeyType': 'HASH'}
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'username', 'AttributeType': 'S'}
                ],
                ProvisionedThroughput={
                    'ReadCapacityUnits': 5,
                    'WriteCapacityUnits': 5
                }
            )
            table.wait_until_exists()
            return table
        else:
            raise

def create_user(username: str, email: str, password_hash: str, otp: str = None):
    table = get_table()
    table.put_item(
        Item={
            'username': username,
            'email': email,
            'password_hash': password_hash,
            'is_verified': False,
            'otp': otp,
            'registration_timestamp': Decimal(str(time.time()))
        },
        ConditionExpression='attribute_not_exists(username)'
    )

def get_user(username: str):
    table = get_table()
    response = table.get_item(Key={'username': username})
    return response.get('Item')

def verify_user(username: str):
    table = get_table()
    table.update_item(
        Key={'username': username},
        UpdateExpression="SET is_verified = :val REMOVE otp",
        ExpressionAttributeValues={':val': True}
    )

def set_otp(username: str, otp: str):
    table = get_table()
    table.update_item(
        Key={'username': username},
        UpdateExpression="SET otp = :val",
        ExpressionAttributeValues={':val': otp}
    )


def update_profile_pic(username: str, url: str):
    table = get_table()
    table.update_item(
        Key={'username': username},
        UpdateExpression="SET profile_pic_url = :u",
        ExpressionAttributeValues={':u': url},
    )


def get_profile_pic_url(username: str) -> str:
    user = get_user(username)
    if not user:
        return ""
    return user.get("profile_pic_url") or ""


MESSAGES_TABLE_NAME = 'ChatboxMessages'

def get_messages_table():
    try:
        table = dynamodb.Table(MESSAGES_TABLE_NAME)
        table.load()
        return table
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            table = dynamodb.create_table(
                TableName=MESSAGES_TABLE_NAME,
                KeySchema=[
                    {'AttributeName': 'room_id', 'KeyType': 'HASH'},
                    {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'room_id', 'AttributeType': 'S'},
                    {'AttributeName': 'timestamp', 'AttributeType': 'N'}
                ],
                ProvisionedThroughput={
                    'ReadCapacityUnits': 5,
                    'WriteCapacityUnits': 5
                }
            )
            table.wait_until_exists()
            return table
        else:
            raise


def save_message(
    sender: str,
    content: str,
    attachment_url: str | None = None,
    attachment_filename: str | None = None,
    attachment_mime: str | None = None,
):
    table = get_messages_table()
    timestamp = Decimal(str(time.time()))
    text = (content or "").strip()
    if not text:
        if attachment_filename:
            text = f"📎 {attachment_filename}"
        elif attachment_url:
            text = "📎 Attachment"

    item = {
        'room_id': 'global',
        'timestamp': timestamp,
        'sender': sender,
        'content': text,
    }
    if attachment_url:
        item['attachment_url'] = attachment_url
        item['attachment_filename'] = attachment_filename or 'file'
        item['attachment_mime'] = attachment_mime or 'application/octet-stream'

    table.put_item(Item=item)

def get_recent_messages(username: str, limit: int = 10):
    user = get_user(username)
    if not user:
        return []
    
    # If the user was created before this update, default to 0 so they see everything
    reg_time = user.get('registration_timestamp', Decimal('0'))

    table = get_messages_table()
    response = table.query(
        KeyConditionExpression=Key('room_id').eq('global') & Key('timestamp').gte(reg_time),
        ScanIndexForward=False, # Newest first to easily limit
        Limit=limit
    )
    items = response.get('Items', [])
    # Reverse so they are returned in chronological order (oldest to newest)
    items.reverse()
    senders = {item["sender"] for item in items}
    pic_by_sender = {s: get_profile_pic_url(s) for s in senders}
    # Convert Decimals for JSON serialization and attach avatar URLs
    for item in items:
        item["timestamp"] = float(item["timestamp"])
        item["profile_pic_url"] = pic_by_sender.get(item["sender"], "")

    return items
