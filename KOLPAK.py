import vk_api
import time
import json
import os
import sys
import re
from datetime import datetime, timedelta
from collections import defaultdict
from vk_api.exceptions import ApiError

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_FILE = os.path.join(SCRIPT_DIR, 'progress.json')
TIMEOUT = 30
MAX_RETRIES = 3
TOKEN_EXPIRY_HOURS = 24

LOGO = r"""
 _____ _____ __    _____ _____ _____    
|  |  |     |  |  |  _  |  _  |  |  |  
|    -|  |  |  |__|   __|     |    -|  
|__|__|_____|_____|__|  |__|__|__|__|  
"""

def get_input(prompt):
    while True:
        try:
            value = input(prompt).strip()
            return value
        except EOFError:
            print("Input error, try again")
        except KeyboardInterrupt:
            print("\nInterrupted")
            sys.exit(0)

def get_yes_no(prompt):
    while True:
        answer = get_input(prompt + " (y/n): ").lower()
        if answer in ['y', 'yes', '1', 'true']:
            return True
        elif answer in ['n', 'no', '0', 'false']:
            return False
        else:
            print("Please enter y or n")

def extract_token_from_url(url_or_token):
    if 'oauth.vk.ru' in url_or_token or 'vk.com' in url_or_token:
        match = re.search(r'access_token=([^&]+)', url_or_token)
        if match:
            return match.group(1)
        else:
            print("Failed to extract token from URL")
            return None
    else:
        return url_or_token

def get_group_id(api, group_identifier):
    if 'vk.com/' in group_identifier or 'vk.ru/' in group_identifier:
        if 'vk.com/' in group_identifier:
            group_identifier = group_identifier.split('vk.com/')[-1].split('/')[0]
        else:
            group_identifier = group_identifier.split('vk.ru/')[-1].split('/')[0]
        if group_identifier.startswith('@'):
            group_identifier = group_identifier[1:]
    
    if group_identifier.isdigit():
        try:
            group_info = api.groups.getById(group_id=group_identifier)
            if group_info:
                return -group_info[0]['id']
        except:
            pass
    
    try:
        group_info = api.groups.getById(group_id=group_identifier)
        if group_info:
            return -group_info[0]['id']
    except ApiError as e:
        if e.code == 100:
            pass
        else:
            print(f"Error getting group by name: {e}")
    
    try:
        resolved = api.utils.resolveScreenName(screen_name=group_identifier)
        if resolved:
            if resolved['type'] == 'group' or resolved['type'] == 'page':
                return -resolved['object_id']
            elif resolved['type'] == 'user':
                return resolved['object_id']
    except:
        pass
    
    if group_identifier.startswith('-') and group_identifier[1:].isdigit():
        return int(group_identifier)
    
    return None

def get_group_info(api, owner_id):
    try:
        group_id = -owner_id if owner_id < 0 else owner_id
        info = api.groups.getById(group_id=group_id, fields=['name', 'screen_name'])
        if info:
            return info[0]
    except:
        pass
    return None

def get_user_info(api, user_ids):
    if not user_ids:
        return {}
    
    try:
        result = {}
        user_list = list(user_ids)
        for i in range(0, len(user_list), 1000):
            chunk = user_list[i:i+1000]
            users = api.users.get(user_ids=chunk, fields=['first_name', 'last_name'])
            for user in users:
                result[user['id']] = f"{user['first_name']} {user['last_name']}"
            time.sleep(0.34)
        return result
    except Exception as e:
        print(f"Error getting user names: {e}")
        return {}

def get_group_posts_count(api, owner_id):
    try:
        posts = api.wall.get(owner_id=owner_id, count=0, filter='all')
        return posts.get('count', 0)
    except ApiError as e:
        print(f"Error getting posts count: {e}")
        return 0

def load_progress():
    if os.path.exists(SAVE_FILE):
        try:
            with open(SAVE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {
                'token': None,
                'token_timestamp': None,
                'group_id': None, 
                'group_name': None,
                'offset': 0, 
                'total_posts': 0,
                'docs': [], 
                'media': [],
                'authors': []
            }
    return {
        'token': None,
        'token_timestamp': None,
        'group_id': None, 
        'group_name': None,
        'offset': 0, 
        'total_posts': 0,
        'docs': [], 
        'media': [],
        'authors': []
    }

def save_progress(token, group_id, group_name, offset, total_posts, docs, media, authors):
    with open(SAVE_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'token': token,
            'token_timestamp': datetime.now().isoformat(),
            'group_id': group_id,
            'group_name': group_name,
            'offset': offset,
            'total_posts': total_posts,
            'docs': docs,
            'media': media,
            'authors': authors
        }, f, ensure_ascii=False, indent=2)

def is_token_expired(token_timestamp):
    if not token_timestamp:
        return True
    try:
        token_time = datetime.fromisoformat(token_timestamp)
        if datetime.now() - token_time > timedelta(hours=TOKEN_EXPIRY_HOURS):
            return True
    except:
        return True
    return False

def progress_bar(current, total, width=40):
    if total == 0:
        return "[" + " " * width + "] 0%"
    
    progress = min(current / total, 1.0)
    filled = int(width * progress)
    bar = "[" + "█" * filled + " " * (width - filled) + "]"
    percent = int(progress * 100)
    return f"{bar} {percent:3d}%"

def update_progress(current, total, docs_count, media_count, authors_count):
    bar = progress_bar(current, total)
    stats = f"P:{current}/{total} D:{docs_count} M:{media_count} A:{authors_count}"
    line = f"{bar} | {stats}"
    
    sys.stdout.write('\r' + ' ' * len(line))
    sys.stdout.write('\r' + line)
    sys.stdout.flush()

def get_wall_posts_with_retry(api, owner_id, offset, retries=MAX_RETRIES):
    for attempt in range(retries):
        try:
            return api.wall.get(
                owner_id=owner_id,
                offset=offset,
                count=100,
                filter='all',
                timeout=TIMEOUT
            )
        except ApiError as e:
            if e.code == 9:
                wait_time = min(5, 1.5 ** (attempt + 1))
                time.sleep(wait_time)
                continue
            elif e.code == 6:
                time.sleep(2)
                continue
            elif e.code == 1:
                time.sleep(1)
                continue
            else:
                print(f"\n[API ERROR {e.code}] {e}")
                if attempt < retries - 1:
                    time.sleep(3)
                    continue
                return None
        except Exception as e:
            print(f"\n[NETWORK ERROR] {e}")
            if attempt < retries - 1:
                time.sleep(3)
                continue
            return None
    return None

def is_personal_page(owner_id):
    return owner_id > 0

def is_group_post(post, group_owner_id):
    from_id = post.get('from_id')
    signer_id = post.get('signer_id')
    
    if from_id == group_owner_id:
        return True
    if signer_id is not None:
        return True
    return False

def is_community_comment(comment, group_owner_id):
    from_id = comment.get('from_id')
    if from_id:
        return from_id == group_owner_id
    return False

def process_attachments(attachments, group_owner_id, post_id, post_author_id=None, is_comment=False):
    result = {
        'docs': [],
        'media': [],
        'authors': []
    }
    
    post_url = f"https://vk.com/wall{group_owner_id}_{post_id}"
    
    for attachment in attachments:
        att_type = attachment.get('type')
        
        if att_type == 'doc':
            doc_owner = attachment['doc']['owner_id']
            if is_personal_page(doc_owner):
                result['docs'].append({
                    'owner_id': doc_owner,
                    'post_url': post_url
                })
        
        elif att_type == 'photo':
            sizes = attachment['photo'].get('sizes', [])
            if sizes:
                photo_owner = attachment['photo'].get('owner_id')
                if photo_owner and photo_owner != group_owner_id and is_personal_page(photo_owner):
                    result['media'].append({
                        'owner_id': photo_owner,
                        'post_url': post_url,
                        'type': 'photo'
                    })
        
        elif att_type == 'video':
            video_owner = attachment['video'].get('owner_id')
            if video_owner and video_owner != group_owner_id and is_personal_page(video_owner):
                result['media'].append({
                    'owner_id': video_owner,
                    'post_url': post_url,
                    'type': 'video'
                })
    
    if not is_comment and post_author_id and is_personal_page(post_author_id):
        result['authors'].append({
            'owner_id': post_author_id,
            'post_url': post_url
        })
    
    return result

def get_post_comments_batch(api, owner_id, post_ids, group_owner_id):
    if not post_ids:
        return {}
    
    code = "var result = {};"
    
    for i, post_id in enumerate(post_ids):
        var_name = f"c{i}"
        code += f"""
        var {var_name} = API.wall.getComments({{
            owner_id: {owner_id},
            post_id: {post_id},
            count: 100,
            need_likes: 0
        }});
        result["{post_id}"] = {var_name};
        """
    
    code += "return result;"
    
    try:
        response = api.execute(code=code)
        return response
    except ApiError as e:
        if e.code == 9:
            time.sleep(1)
            return get_post_comments_batch(api, owner_id, post_ids, group_owner_id)
        else:
            print(f"\n[EXECUTE ERROR] {e}")
            return {}
    except Exception as e:
        print(f"\n[EXECUTE ERROR] {e}")
        return {}

def process_comments_batch(comments_data, group_owner_id):
    result = {'docs': [], 'media': []}
    
    for post_id, comments in comments_data.items():
        if not comments or 'items' not in comments:
            continue
        
        for comment in comments['items']:
            if not is_community_comment(comment, group_owner_id):
                continue
            
            if 'attachments' in comment:
                comment_data = process_attachments(
                    comment['attachments'], 
                    group_owner_id,
                    int(post_id),
                    is_comment=True
                )
                result['docs'].extend(comment_data['docs'])
                result['media'].extend(comment_data['media'])
    
    return result

def main(show_logo=True):
    if show_logo:
        print(LOGO)
    
    progress = load_progress()
    saved_token = progress.get('token')
    token_timestamp = progress.get('token_timestamp')
    saved_group_id = progress.get('group_id')
    saved_group_name = progress.get('group_name')
    saved_offset = progress.get('offset', 0)
    saved_total = progress.get('total_posts', 0)
    
    token = None
    if saved_token and not is_token_expired(token_timestamp):
        token = saved_token
        print("\n[TOKEN] Using saved token")
    else:
        if saved_token:
            print("\n[TOKEN] Saved token expired")
        
        while True:
            token_input = get_input("\nToken or token URL: ")
            if not token_input:
                print("Token cannot be empty")
                continue
            
            token = extract_token_from_url(token_input)
            if not token:
                print("Invalid token, try again")
                continue
            
            try:
                vk_session = vk_api.VkApi(token=token)
                vk_test = vk_session.get_api()
                vk_test.users.get()
                break
            except Exception as e:
                print(f"Invalid token: {e}")
                continue
    
    group_id = None
    group_name = None
    offset = 0
    total_posts = 0
    all_docs = []
    all_media = []
    all_authors = []
    parse_comments = False
    
    if saved_group_id and saved_offset > 0 and saved_offset < saved_total:
        print(f"\n[SAVED PROGRESS] Found incomplete session")
        print(f"  Group: {saved_group_name or saved_group_id}")
        print(f"  Progress: {saved_offset}/{saved_total} posts")
        print(f"  Found: {len(progress.get('docs', []))} docs, {len(progress.get('media', []))} media, {len(progress.get('authors', []))} authors")
        
        load_saved = get_yes_no("Load saved progress?")
        if load_saved:
            group_id = saved_group_id
            group_name = saved_group_name
            offset = saved_offset
            total_posts = saved_total
            all_docs = progress.get('docs', [])
            all_media = progress.get('media', [])
            all_authors = progress.get('authors', [])
            parse_comments = get_yes_no("Parse comments?")
    
    if not group_id:
        while True:
            group_input = get_input("\nGroup (name, ID or URL): ")
            if not group_input:
                print("Group cannot be empty")
                continue
            
            try:
                vk_session = vk_api.VkApi(token=token)
                vk = vk_session.get_api()
                
                group_id = get_group_id(vk, group_input)
                if not group_id:
                    print(f"Group '{group_input}' not found, try again")
                    continue
                
                if group_id > 0:
                    print(f"Warning: Got positive ID {group_id}, negating for group API")
                    group_id = -group_id
                
                break
            except Exception as e:
                print(f"Error: {e}")
                continue
        
        parse_comments = get_yes_no("Parse comments?")
        
        try:
            vk_session = vk_api.VkApi(token=token)
            vk = vk_session.get_api()
        except Exception as e:
            print(f"Auth error: {e}")
            return
        
        group_info = get_group_info(vk, group_id)
        group_name = group_info.get('name', str(group_id)) if group_info else str(group_id)
        
        total_posts = get_group_posts_count(vk, group_id)
        if total_posts == 0:
            print("No posts found")
            return
        
        offset = 0
        all_docs = []
        all_media = []
        all_authors = []
        
        save_progress(token, group_id, group_name, 0, total_posts, [], [], [])
    
    try:
        vk_session = vk_api.VkApi(token=token)
        vk = vk_session.get_api()
        vk.users.get()
    except Exception as e:
        print(f"Auth error: {e}")
        return
    
    if not group_name:
        group_info = get_group_info(vk, group_id)
        group_name = group_info.get('name', str(group_id)) if group_info else str(group_id)
    
    print(f"\n{group_name} ({group_id})")
    
    start_time = time.time()
    consecutive_errors = 0
    
    try:
        while offset < total_posts:
            try:
                update_progress(offset, total_posts, len(all_docs), len(all_media), len(all_authors))
                
                posts_data = get_wall_posts_with_retry(vk, group_id, offset)
                
                if posts_data is None:
                    consecutive_errors += 1
                    if consecutive_errors >= 5:
                        save_progress(token, group_id, group_name, offset, total_posts, all_docs, all_media, all_authors)
                        time.sleep(30)
                        consecutive_errors = 0
                    else:
                        time.sleep(2)
                    continue
                
                if not posts_data.get('items'):
                    break
                
                post_ids_for_comments = []
                
                for post in posts_data['items']:
                    post_id = post.get('id')
                    signer_id = post.get('signer_id')
                    
                    if not is_group_post(post, group_id):
                        continue
                    
                    author_id = signer_id if signer_id and is_personal_page(signer_id) else None
                    
                    if 'attachments' in post:
                        post_data = process_attachments(
                            post['attachments'], 
                            group_id,
                            post_id,
                            author_id,
                            is_comment=False
                        )
                        
                        all_docs.extend(post_data['docs'])
                        all_media.extend(post_data['media'])
                        all_authors.extend(post_data['authors'])
                    
                    if parse_comments:
                        post_ids_for_comments.append(post_id)
                
                if parse_comments and post_ids_for_comments:
                    batch_size = 25
                    for i in range(0, len(post_ids_for_comments), batch_size):
                        batch = post_ids_for_comments[i:i+batch_size]
                        comments_data = get_post_comments_batch(vk, group_id, batch, group_id)
                        if comments_data:
                            processed = process_comments_batch(comments_data, group_id)
                            all_docs.extend(processed['docs'])
                            all_media.extend(processed['media'])
                        
                        time.sleep(0.34)
                
                offset += len(posts_data['items'])
                consecutive_errors = 0
                
                if offset % 50 == 0:
                    save_progress(token, group_id, group_name, offset, total_posts, all_docs, all_media, all_authors)
                
                time.sleep(0.34)
                
            except KeyboardInterrupt:
                print("\n\nInterrupted. Saving progress...")
                save_progress(token, group_id, group_name, offset, total_posts, all_docs, all_media, all_authors)
                print("Progress saved. Press Enter to exit...")
                input()
                return
            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    save_progress(token, group_id, group_name, offset, total_posts, all_docs, all_media, all_authors)
                    time.sleep(10)
                    consecutive_errors = 0
                else:
                    time.sleep(2)
                continue
        
        update_progress(total_posts, total_posts, len(all_docs), len(all_media), len(all_authors))
        print("\n")
        
        all_user_ids = set()
        for doc in all_docs:
            all_user_ids.add(doc['owner_id'])
        for media in all_media:
            all_user_ids.add(media['owner_id'])
        for author in all_authors:
            all_user_ids.add(author['owner_id'])
        
        user_names = get_user_info(vk, all_user_ids)
        
        doc_dict = defaultdict(list)
        for item in all_docs:
            doc_dict[item['owner_id']].append(item['post_url'])
        
        media_dict = defaultdict(list)
        for item in all_media:
            media_dict[item['owner_id']].append(item['post_url'])
        
        author_dict = defaultdict(list)
        for item in all_authors:
            author_dict[item['owner_id']].append(item['post_url'])
        
        elapsed = time.time() - start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_group_name = re.sub(r'[^\w\s-]', '', group_name).strip().replace(' ', '_')
        output_file = f"results_{safe_group_name}_{timestamp}.txt"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"RESULTS FOR GROUP: {group_name}\n")
            f.write(f"Group ID: {group_id}\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Posts processed: {offset}\n")
            f.write(f"Comments parsed: {'Yes' if parse_comments else 'No'}\n")
            f.write(f"Time: {hours:02d}:{minutes:02d}:{seconds:02d}\n\n")
            
            if doc_dict:
                f.write(f"DOCUMENT OWNERS (files, GIFs, etc.): {len(doc_dict)}\n")
                f.write("-" * 75 + "\n")
                for owner_id in sorted(doc_dict.keys()):
                    name = user_names.get(owner_id, 'Unknown')
                    posts = sorted(set(doc_dict[owner_id]))
                    f.write(f"{name} | https://vk.com/id{owner_id}\n")
                    f.write(f"  Posts: {', '.join(posts)}\n\n")
                f.write("\n")
            
            if media_dict:
                f.write(f"MEDIA OWNERS (photos, videos): {len(media_dict)}\n")
                f.write("-" * 75 + "\n")
                for owner_id in sorted(media_dict.keys()):
                    name = user_names.get(owner_id, 'Unknown')
                    posts = sorted(set(media_dict[owner_id]))
                    f.write(f"{name} | https://vk.com/id{owner_id}\n")
                    f.write(f"  Posts: {', '.join(posts)}\n\n")
                f.write("\n")
            
            if author_dict:
                f.write(f"POST AUTHORS (users who signed posts): {len(author_dict)}\n")
                f.write("-" * 75 + "\n")
                for owner_id in sorted(author_dict.keys()):
                    name = user_names.get(owner_id, 'Unknown')
                    posts = sorted(set(author_dict[owner_id]))
                    f.write(f"{name} | https://vk.com/id{owner_id}\n")
                    f.write(f"  Posts: {', '.join(posts)}\n\n")
        
        save_progress(token, group_id, group_name, offset, total_posts, all_docs, all_media, all_authors)
        
        print(f"Results saved to: {output_file}")
        print("\nPress Enter to restart...")
        input()
        
        main(show_logo=False)
    
    except Exception as e:
        print(f"\n[CRITICAL ERROR] {e}")
        save_progress(token, group_id, group_name, offset, total_posts, all_docs, all_media, all_authors)
        print("Progress saved. Press Enter to restart...")
        input()
        main(show_logo=False)

if __name__ == '__main__':
    try:
        main(show_logo=True)
    except KeyboardInterrupt:
        print("\nProgram stopped")
    except Exception as e:
        print(f"\nCritical error: {e}")
        import traceback
        traceback.print_exc()
        input("Press Enter to restart...")
        main(show_logo=False)
