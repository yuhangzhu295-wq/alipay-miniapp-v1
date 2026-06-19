# Project Plan: Frontend Layout Download Option

## Objectives
Implement a download option in the ID photo frontend to allow users to choose between downloading a single ID photo or a 6-inch layout photo, when the backend returns a `layoutUrl`.

## Milestones

### Milestone 1: Backend API Extension
- Modify `/api/id-photo/compose` in `server/main.py` to return the `layoutUrl` field in the success response.
- **Verification**: Programmatic API check shows `layoutUrl` in response when compose endpoint is called.

### Milestone 2: Frontend API & Page Integration
- Update `utils/aiImageApi.js` to parse and return `layoutUrl` from compose and generate responses.
- Modify `pages/generate/generate.js` to store `layoutUrl` and display a `wx.showActionSheet` choice between "下载单张照片" and "下载六寸排版照" when `layoutUrl` is available.
- Modify `pages/result/result.js` to load `layoutUrl` and provide the same action sheet download flow.
- **Verification**: Frontend Javascript files successfully handle `layoutUrl` and trigger downloading/saving correctly.

### Milestone 3: Automated Verification & Regression Testing
- Update `server/scripts/verify_frontend_ui.py` to assert that the `savePhoto` flow triggers `wx.showActionSheet` with the single and layout download options when `layoutUrl` is present.
- Run `npm run verify:frontend-ui` and other regression tests (`npm run verify:full-business-flow`, `node server/scripts/verify_devtools_business_flow.js`) to confirm all checks pass.
- **Verification**: All verify tests pass.
