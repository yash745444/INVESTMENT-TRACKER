# Auth Testing Playbook

## MongoDB verification
```
mongosh
use test_database
db.users.find({role: "admin"}).pretty()
```
Verify: bcrypt hash starts with `$2b$`, unique index on users.email, index on login_attempts.identifier.

## API testing
```
curl -c cookies.txt -X POST $API/api/auth/login -H "Content-Type: application/json" -d '{"email":"yash.sojitra34@gmail.com","password":"Yash@2026"}'
curl -b cookies.txt $API/api/auth/me
```
Login returns the user object and sets `access_token` + `refresh_token` httpOnly cookies. `/me` returns the same user with those cookies. Bearer header also works: `Authorization: Bearer <access_token>`.

## Brute force
5 failed logins for the same ip:email locks for 15 minutes (HTTP 429).
