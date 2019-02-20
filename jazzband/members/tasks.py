from datetime import timedelta

from spinach import Tasks

from ..config import ONE_MINUTE
from ..db import postgres, redis
from ..github import github
from .models import EmailAddress, User

tasks = Tasks()



@tasks.task(name='sync_members', periodicity=timedelta(seconds=60))
def sync_members():
    # use a lock to make sure we don't run this multiple times
    with redis.lock("sync_members", ttl=ONE_MINUTE):

        members_data = github.get_members()
        User.sync(members_data)

        stored_ids = set(user.id for user in User.query.all())
        fetched_ids = set(m['id'] for m in members_data)
        stale_ids = stored_ids - fetched_ids
        if stale_ids:
            User.query.filter(
                User.id.in_(stale_ids)
            ).update({'is_member': False}, 'fetch')
            postgres.session.commit()


@tasks.task(name='sync_email_addresses', max_retries=5)
def sync_email_addresses(user_id, access_token=None):
    "Sync email addresses for user"
    with redis.lock("sync_email_addresses", ttl=ONE_MINUTE):
        user = User.query.get(User.id == user_id)

        email_addresses = []
        access_token = access_token or user.access_token
        email_data = github.get_emails(access_token=access_token)

        for email_item in email_data:
            email_item['user_id'] = user.id
            email_addresses.append(email_item)

        EmailAddress.sync(email_addresses, key='email')

        return email_addresses
