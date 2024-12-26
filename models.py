from tortoise.models import Model
from tortoise import fields

import datetime

class BaseModel(Model):
    id = fields.IntField(pk=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        abstract = True

class TelegramUser(BaseModel):

    telegram_id = fields.IntField()
    username = fields.CharField(max_length=255, null=True)
    first_name = fields.CharField(max_length=255, null=True)
    last_name = fields.CharField(max_length=255, null=True)

    vector_storage_volume = fields.FloatField(default=0)

    @property
    async def last_24_hours_messages_count(self):
        return await self.user_messages.filter(
            created_at__gte=datetime.datetime.now() - datetime.timedelta(days=1)
        ).count()

    @property
    async def limmits_not_exceeded(self):
        return await self.last_24_hours_messages_count <= 30 and self.vector_storage_volume <= 200

    subscription_end_date = fields.DatetimeField(null=True)

    async def activate_subscription(self, days=30):
        self.subscription_end_date = datetime.datetime.now() + datetime.timedelta(days=days)
        await self.save()

    async def has_active_subscription(self):
        return self.subscription_end_date and self.subscription_end_date > datetime.datetime.now()

    def __str__(self):
        return self.username
    

class Note(BaseModel):

    text = fields.TextField()
    user = fields.ForeignKeyField('models.TelegramUser', related_name='notes')
    telegram_message_id = fields.IntField()

    def __str__(self):
        return self.text[:20]

class UserMessage(BaseModel):

    text = fields.TextField()
    user = fields.ForeignKeyField('models.TelegramUser', related_name='user_messages')
    telegram_message_id = fields.IntField()

    def __str__(self):
        return self.text[:20]