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

    index_name = fields.CharField(max_length=255, null=True)
    vector_storage_volume = fields.FloatField(default=0)
    queries_count = fields.IntField(default=0)

    invited_by = fields.ForeignKeyField('models.TelegramUser', related_name='invited_users', null=True)

    # Not needed thanks to from aiogram.utils.deep_linking import create_start_link
    # @property
    # async def invite_link(self):
    #     return f'{TG_BOT_LINK}?start={self.telegram_id}'

    @property
    async def invited_users_count(self):
        invited_users = await self.invited_users.filter(subscription_end_date__isnull=False)
        return len(invited_users)

    @property
    def vector_storage_namespace(self):
        return f'user_{self.telegram_id}_notes'

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

        current_end_date = self.subscription_end_date if self.subscription_end_date else datetime.datetime.now()
        current_end_date += datetime.timedelta(days=days)
        self.subscription_end_date = current_end_date

        await self.save()

    async def has_active_subscription(self):

        if not self.subscription_end_date:
            return False

        return self.subscription_end_date >= datetime.datetime.now()

    def __str__(self):
        return self.username
    

class Note(BaseModel):

    text = fields.TextField()
    user = fields.ForeignKeyField('models.TelegramUser', related_name='notes')
    telegram_message_id = fields.IntField()
    is_vectorized = fields.BooleanField(default=False)

    def __str__(self):
        return self.text[:20]

class UserMessage(BaseModel):

    text = fields.TextField()
    user = fields.ForeignKeyField('models.TelegramUser', related_name='user_messages')
    telegram_message_id = fields.IntField()

    def __str__(self):
        return self.text[:20]