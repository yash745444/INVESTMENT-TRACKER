# Auth Testing Playbook

This app has TWO auth flows:
1. Email/password (admin): JWT httpOnly cookies (access_token + refresh_token)
2. Google OAuth (Emergent-managed): session_token httpOnly cookie (7 days, stored in db.user_sessions)

## Test user + session (Google flow simulation)
```bash
mongosh --eval "
use('test_database');
var userId = new ObjectId();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({
  _id: userId,
  email: 'test.user.' + Date.now() + '@example.com',
  name: 'Test User', role: 'user', status: 'approved',
  created_at: new Date().toISOString()
});
db.user_sessions.insertOne({
  user_id: userId.toString(),
  session_token: sessionToken,
  expires_at: new Date(Date.now() + 7*24*60*60*1000).toISOString(),
  created_at: new Date().toISOString()
});
print('Session token: ' + sessionToken);
"
```

## API testing
```
curl -X GET "$API/api/auth/me" -H "Authorization: Bearer YOUR_SESSION_TOKEN"
```
`/me` returns the user for both JWT access_token and session_token (Bearer or cookie).

## Browser testing
```js
await page.context.add_cookies([{
  "name": "session_token", "value": "YOUR_SESSION_TOKEN",
  "domain": "your-app-host", "path": "/",
  "httpOnly": true, "secure": true, "sameSite": "None"
}]);
await page.goto("https://your-app-host");
```

## Admin login (email/password)
- POST /api/auth/login {email: yash.sojitra34@gmail.com, password: Yash@2026}
- Sets access_token + refresh_token cookies; /api/auth/me returns admin.

## Approval gating
- Users with status != "approved" get 403 {"detail":"pending_approval"} on all data endpoints; /api/auth/me and /api/auth/logout still work.
- Admin: GET /api/admin/users, POST /api/admin/users/{id}/status {status}, DELETE /api/admin/users/{id} (admin role required).

## Brute force
5 failed logins for same ip:email locks 15 minutes (HTTP 429).

## Google OAuth redirect
Login button: `https://auth.emergentagent.com/?redirect=${window.location.origin}/` — returns to app with #session_id=..., frontend POSTs to /api/auth/google/session.
REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH

## Cleanup test data
```bash
mongosh --eval "
use('test_database');
db.users.deleteMany({email: /test\.user\./});
db.user_sessions.deleteMany({session_token: /test_session/});
"
```
