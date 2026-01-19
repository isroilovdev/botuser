import asyncio
import logging
from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, FloodWaitError
from config import API_ID, API_HASH, BOT_TOKEN, ADMIN_ID
from db import Database
from mtproto import MTProtoManager
from scheduler import Scheduler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

user_states = {}

async def start_handler(event):
    user_id = event.sender_id
    user = event.client.db.get_user(user_id)
    
    markup = [[Button.inline("👥 Profil", b"profile")]]
    if user:
        markup.append([Button.inline("💬 Elon", b"message")])
        markup.append([Button.inline("▶️ Boshqaruv", b"control")])
    
    if user_id == ADMIN_ID:
        markup.append([Button.inline("🔧 Admin Panel", b"admin")])
    
    text = "🚕 Taksi haydovchilari uchun avto-posting tizimi\n\n"
    if user:
        status = "✅ Faol" if event.client.scheduler.is_active(user_id) else "⏸ To'xtatilgan"
        text += f"Status: {status}\n\n"
    text += "Guruhga avtomatik xabar yuborish uchun profilingizni sozlang."
    
    try:
        await event.edit(text, buttons=markup)
    except:
        await event.respond(text, buttons=markup)

async def profile_handler(event):
    user_id = event.sender_id
    user = event.client.db.get_user(user_id)
    
    if user:
        markup = [
            [Button.inline("🗑 Profilni o'chirish", b"delete_profile")],
            [Button.inline("🔙 Orqaga", b"back_main")]
        ]
        text = f"👥 Profil boshqaruvi\n\n✅ Profil mavjud\nTelefon: {user['phone']}"
    else:
        markup = [
            [Button.inline("➕ Profil qo'shish", b"add_profile")],
            [Button.inline("🔙 Orqaga", b"back_main")]
        ]
        text = "👥 Profil boshqaruvi\n\n❌ Profil topilmadi"
    
    await event.edit(text, buttons=markup)

async def add_profile_handler(event):
    user_id = event.sender_id
    user_states[user_id] = {'step': 'phone'}
    
    await event.edit(
        "📱 Telefon raqamingizni yuboring:\n\n"
        "Format: +998XXXXXXXXX",
        buttons=[
            [Button.request_phone("📱 Raqamni yuborish")],
            [Button.inline("🔙 Bekor qilish", b"profile")]
        ]
    )

async def message_handler(event):
    user_id = event.sender_id
    
    if user_id not in user_states:
        return
    
    state = user_states[user_id]
    
    if user_id == ADMIN_ID:
        if state.get('step') == 'admin_set_target':
            try:
                group_id = int(event.raw_text.strip())
                event.client.db.set_target_group(group_id)
                await event.respond("✅ Maqsadli guruh o'rnatildi", buttons=[[Button.inline("🔙 Admin Panel", b"admin")]])
                del user_states[ADMIN_ID]
                return
            except ValueError:
                await event.respond("❌ Noto'g'ri format. Raqam kiriting:")
                return
        
        elif state.get('step') == 'admin_set_interval':
            try:
                interval = int(event.raw_text.strip())
                if interval < 60:
                    await event.respond("❌ Interval kamida 60 soniya bo'lishi kerak")
                    return
                event.client.db.set_interval(interval)
                await event.respond(f"✅ Interval {interval} soniyaga o'rnatildi", buttons=[[Button.inline("🔙 Admin Panel", b"admin")]])
                del user_states[ADMIN_ID]
                return
            except ValueError:
                await event.respond("❌ Noto'g'ri format. Raqam kiriting:")
                return
    
    if state.get('step') == 'phone':
        if event.contact:
            phone = event.contact.phone_number
        else:
            phone = event.raw_text.strip()
            if not phone.startswith('+'):
                phone = '+' + phone
        
        try:
            client = await event.client.mtproto_mgr.create_client(user_id)
            await client.connect()
            
            result = await client.send_code_request(phone)
            state['phone'] = phone
            state['phone_hash'] = result.phone_code_hash
            state['step'] = 'code'
            state['client'] = client
            state['code_time'] = asyncio.get_event_loop().time()
            
            await event.respond(
                "✉️ Telegramdan kelgan kodni kiriting:\n\n"
                "Format: 12345",
                buttons=[
                    [Button.inline("📱 Kod kelmadi", b"resend_code")],
                    [Button.inline("🔙 Bekor qilish", b"cancel_login")]
                ]
            )
        except FloodWaitError as e:
            await event.respond(f"⏳ {e.seconds} soniyadan keyin qayta urinib ko'ring", buttons=[[Button.inline("🔙 Orqaga", b"profile")]])
            del user_states[user_id]
        except Exception as e:
            logger.error(f"Phone error: {e}")
            await event.respond("❌ Xatolik yuz berdi. Qayta urinib ko'ring", buttons=[[Button.inline("🔙 Orqaga", b"profile")]])
            del user_states[user_id]
    
    elif state.get('step') == 'code':
        code = event.raw_text.strip().replace('.', '').replace('-', '').replace(' ', '')
        client = state['client']
        
        try:
            await client.sign_in(state['phone'], code, phone_code_hash=state['phone_hash'])
            
            session_str = event.client.mtproto_mgr.save_session(user_id, client)
            event.client.db.add_user(user_id, state['phone'], session_str)
            
            await event.respond("✅ Profil muvaffaqiyatli qo'shildi!", buttons=[[Button.inline("🏠 Bosh menu", b"back_main")]])
            del user_states[user_id]
            
        except SessionPasswordNeededError:
            state['step'] = '2fa'
            await event.respond("🔐 2FA parolini kiriting:", buttons=[[Button.inline("🔙 Bekor qilish", b"cancel_login")]])
            
        except PhoneCodeInvalidError:
            await event.respond("❌ Noto'g'ri kod. Qayta kiriting:")
            
        except Exception as e:
            logger.error(f"Code error: {e}")
            await event.respond("❌ Xatolik yuz berdi", buttons=[[Button.inline("🔙 Orqaga", b"profile")]])
            del user_states[user_id]
    
    elif state.get('step') == '2fa':
        password = event.raw_text.strip()
        client = state['client']
        
        try:
            await client.sign_in(password=password)
            
            session_str = event.client.mtproto_mgr.save_session(user_id, client)
            event.client.db.add_user(user_id, state['phone'], session_str)
            
            await event.respond("✅ Profil muvaffaqiyatli qo'shildi!", buttons=[[Button.inline("🏠 Bosh menu", b"back_main")]])
            del user_states[user_id]
            
        except Exception as e:
            logger.error(f"2FA error: {e}")
            await event.respond("❌ Noto'g'ri parol. Qayta kiriting:")
    
    elif state.get('step') == 'message_text':
        message_text = event.raw_text.strip()
        event.client.db.save_message(user_id, message_text)
        
        await event.respond("✅ Elon saqlandi!", buttons=[[Button.inline("🏠 Bosh menu", b"back_main")]])
        del user_states[user_id]

async def resend_code_handler(event):
    user_id = event.sender_id
    
    if user_id not in user_states:
        await event.answer("❌ Sessiya yaroqsiz")
        return
    
    state = user_states[user_id]
    elapsed = asyncio.get_event_loop().time() - state.get('code_time', 0)
    
    if elapsed < 60:
        await event.answer(f"⏳ {60 - int(elapsed)} soniyadan keyin qayta yuborishingiz mumkin", alert=True)
        return
    
    try:
        client = state['client']
        result = await client.send_code_request(state['phone'])
        state['phone_hash'] = result.phone_code_hash
        state['code_time'] = asyncio.get_event_loop().time()
        
        await event.answer("✅ Kod qayta yuborildi", alert=True)
    except Exception as e:
        logger.error(f"Resend error: {e}")
        await event.answer("❌ Xatolik", alert=True)

async def cancel_login_handler(event):
    user_id = event.sender_id
    if user_id in user_states:
        if 'client' in user_states[user_id]:
            try:
                await user_states[user_id]['client'].disconnect()
            except:
                pass
        del user_states[user_id]
    await profile_handler(event)

async def delete_profile_handler(event):
    user_id = event.sender_id
    
    await event.edit(
        "⚠️ Profilni o'chirishni tasdiqlaysizmi?\n\n"
        "Bu barcha ma'lumotlaringizni o'chiradi!",
        buttons=[
            [Button.inline("✅ Ha, o'chirish", b"confirm_delete")],
            [Button.inline("❌ Yo'q", b"profile")]
        ]
    )

async def confirm_delete_handler(event):
    user_id = event.sender_id
    
    event.client.scheduler.stop_sender(user_id)
    event.client.mtproto_mgr.delete_session(user_id)
    event.client.db.delete_user(user_id)
    
    await event.edit("✅ Profil o'chirildi", buttons=[[Button.inline("🏠 Bosh menu", b"back_main")]])

async def message_menu_handler(event):
    user_id = event.sender_id
    
    if not event.client.db.get_user(user_id):
        await event.answer("❌ Avval profil qo'shing!", alert=True)
        return
    
    msg = event.client.db.get_message(user_id)
    
    text = "💬 Elon boshqaruvi\n\n"
    if msg:
        text += f"📝 Joriy elon:\n{msg[:200]}{'...' if len(msg) > 200 else ''}"
    else:
        text += "❌ Elon topilmadi"
    
    markup = [
        [Button.inline("✏️ Yangi elon yozish", b"write_message")],
        [Button.inline("🔙 Orqaga", b"back_main")]
    ]
    
    await event.edit(text, buttons=markup)

async def write_message_handler(event):
    user_id = event.sender_id
    user_states[user_id] = {'step': 'message_text'}
    await event.edit(
        "✍️ Yangi elon matnini yuboring:",
        buttons=[[Button.inline("🔙 Bekor qilish", b"message")]]
    )

async def control_handler(event):
    user_id = event.sender_id
    
    if not event.client.db.get_user(user_id):
        await event.answer("❌ Avval profil qo'shing!", alert=True)
        return
    
    if not event.client.db.get_message(user_id):
        await event.answer("❌ Avval elon yozing!", alert=True)
        return
    
    is_active = event.client.scheduler.is_active(user_id)
    target = event.client.db.get_target_group()
    interval = event.client.db.get_interval()
    
    if is_active:
        markup = [[Button.inline("⏹ To'xtatish", b"stop_sending")]]
        status = "✅ Yuborish faol"
    else:
        markup = [[Button.inline("▶️ Boshlash", b"start_sending")]]
        status = "⏸ Yuborish to'xtatilgan"
    
    markup.append([Button.inline("🔙 Orqaga", b"back_main")])
    
    text = f"▶️ Boshqaruv paneli\n\n{status}\n\n"
    text += f"⏱ Interval: {interval} soniya ({interval//60} min {interval%60} sek)\n"
    text += f"🎯 Guruh: {target if target else '❌ Belgilanmagan'}"
    
    await event.edit(text, buttons=markup)

async def start_sending_handler(event):
    user_id = event.sender_id
    
    if not event.client.db.get_user(user_id):
        await event.answer("❌ Profil topilmadi", alert=True)
        return
    
    if not event.client.db.get_message(user_id):
        await event.answer("❌ Elon topilmadi", alert=True)
        return
    
    target = event.client.db.get_target_group()
    if not target:
        await event.answer("❌ Admin hali maqsadli guruhni belgilamagan", alert=True)
        return
    
    event.client.scheduler.start_sender(user_id)
    await event.answer("✅ Yuborish boshlandi!", alert=True)
    await control_handler(event)

async def stop_sending_handler(event):
    user_id = event.sender_id
    event.client.scheduler.stop_sender(user_id)
    await event.answer("⏹ Yuborish to'xtatildi!", alert=True)
    await control_handler(event)

async def back_main_handler(event):
    await start_handler(event)

async def admin_panel_handler(event):
    if event.sender_id != ADMIN_ID:
        await event.answer("❌ Ruxsat yo'q", alert=True)
        return
    
    users = event.client.db.get_all_users()
    active = event.client.scheduler.get_active_count()
    target = event.client.db.get_target_group()
    interval = event.client.db.get_interval()
    
    text = "🔧 Admin Panel\n\n"
    text += f"👥 Foydalanuvchilar: {len(users)}\n"
    text += f"✅ Faol: {active}\n"
    text += f"🎯 Guruh: {target or '❌ Yo\'q'}\n"
    text += f"⏱ Interval: {interval}s"
    
    markup = [
        [Button.inline("🎯 Guruh o'zgartirish", b"admin_target")],
        [Button.inline("⏱ Interval o'zgartirish", b"admin_interval")],
        [Button.inline("👥 Foydalanuvchilar", b"admin_users")],
        [Button.inline("💾 DB yuklash", b"admin_download")],
    ]
    
    if active > 0:
        markup.append([Button.inline("⏹ Barchasini to'xtatish", b"admin_stop_all")])
    
    markup.append([Button.inline("🔙 Orqaga", b"back_main")])
    
    try:
        await event.edit(text, buttons=markup)
    except:
        await event.respond(text, buttons=markup)

async def admin_target_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    
    user_states[ADMIN_ID] = {'step': 'admin_set_target'}
    await event.edit(
        "🎯 Maqsadli guruh ID sini yuboring:\n\n"
        "Masalan: -1001234567890\n\n"
        "ℹ️ Guruh ID ni olish uchun botni guruhga qo'shing va /start yuboring.",
        buttons=[[Button.inline("🔙 Bekor qilish", b"admin")]]
    )

async def admin_interval_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    
    user_states[ADMIN_ID] = {'step': 'admin_set_interval'}
    await event.edit(
        "⏱ Yangi intervalni soniyalarda kiriting:\n\n"
        "Masalan:\n"
        "• 305 = 5 min 5 sek\n"
        "• 600 = 10 min\n"
        "• 3600 = 1 soat",
        buttons=[[Button.inline("🔙 Bekor qilish", b"admin")]]
    )

async def admin_download_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    
    try:
        await event.client.send_file(ADMIN_ID, 'data.db', caption="💾 Database fayli")
        await event.answer("✅ Yuborildi", alert=True)
    except Exception as e:
        logger.error(f"DB download error: {e}")
        await event.answer("❌ Xatolik yuz berdi", alert=True)

async def admin_users_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    
    users = event.client.db.get_all_users()
    text = "👥 Foydalanuvchilar ro'yxati:\n\n"
    
    if users:
        for i, u in enumerate(users, 1):
            status = "✅" if event.client.scheduler.is_active(u['user_id']) else "⏸"
            text += f"{i}. {status} ID: {u['user_id']} | {u['phone']}\n"
    else:
        text = "❌ Foydalanuvchilar yo'q"
    
    await event.edit(text, buttons=[[Button.inline("🔙 Orqaga", b"admin")]])

async def admin_stop_all_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    
    users = event.client.db.get_active_users()
    count = 0
    for user in users:
        event.client.scheduler.stop_sender(user['user_id'])
        count += 1
    
    await event.answer(f"⏹ {count} ta yuborish to'xtatildi", alert=True)
    await admin_panel_handler(event)

async def main():
    logger.info("Bot ishga tushmoqda...")
    
    bot = TelegramClient('bot_session', API_ID, API_HASH)
    
    try:
        await bot.start(bot_token=BOT_TOKEN)
        
        db = Database()
        mtproto_mgr = MTProtoManager()
        scheduler = Scheduler(bot, db, mtproto_mgr)
        
        bot.db = db
        bot.mtproto_mgr = mtproto_mgr
        bot.scheduler = scheduler
        
        bot.add_event_handler(start_handler, events.NewMessage(pattern='/start'))
        bot.add_event_handler(profile_handler, events.CallbackQuery(pattern=b"profile"))
        bot.add_event_handler(add_profile_handler, events.CallbackQuery(pattern=b"add_profile"))
        bot.add_event_handler(resend_code_handler, events.CallbackQuery(pattern=b"resend_code"))
        bot.add_event_handler(cancel_login_handler, events.CallbackQuery(pattern=b"cancel_login"))
        bot.add_event_handler(delete_profile_handler, events.CallbackQuery(pattern=b"delete_profile"))
        bot.add_event_handler(confirm_delete_handler, events.CallbackQuery(pattern=b"confirm_delete"))
        bot.add_event_handler(message_menu_handler, events.CallbackQuery(pattern=b"message"))
        bot.add_event_handler(write_message_handler, events.CallbackQuery(pattern=b"write_message"))
        bot.add_event_handler(control_handler, events.CallbackQuery(pattern=b"control"))
        bot.add_event_handler(start_sending_handler, events.CallbackQuery(pattern=b"start_sending"))
        bot.add_event_handler(stop_sending_handler, events.CallbackQuery(pattern=b"stop_sending"))
        bot.add_event_handler(back_main_handler, events.CallbackQuery(pattern=b"back_main"))
        bot.add_event_handler(admin_panel_handler, events.CallbackQuery(pattern=b"admin"))
        bot.add_event_handler(admin_target_handler, events.CallbackQuery(pattern=b"admin_target"))
        bot.add_event_handler(admin_interval_handler, events.CallbackQuery(pattern=b"admin_interval"))
        bot.add_event_handler(admin_download_handler, events.CallbackQuery(pattern=b"admin_download"))
        bot.add_event_handler(admin_users_handler, events.CallbackQuery(pattern=b"admin_users"))
        bot.add_event_handler(admin_stop_all_handler, events.CallbackQuery(pattern=b"admin_stop_all"))
        bot.add_event_handler(message_handler, events.NewMessage())
        
        await scheduler.restore_senders()
        logger.info("Bot faol! Telegram'da /start bosing")
        await bot.run_until_disconnected()
    
    finally:
        logger.info("Bot yopilmoqda...")
        # Cancel all tasks
        for task in list(scheduler.tasks.values()):
            if not task.done():
                task.cancel()
        # Disconnect clients
        mtproto_mgr.disconnect_all()
        await bot.disconnect()
        logger.info("Bot to'xtatildi")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n✅ Bot to'xtatildi")
    except Exception as e:
        logger.error(f"Fatal error: {e}")