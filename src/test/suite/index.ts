import assert from "node:assert/strict";
import * as vscode from "vscode";


const EXPECTED_COMMANDS = [
  "docferry.copyShareLink",
  "docferry.cancelDetailedNote",
  "docferry.checkDetailedNote",
  "docferry.deleteFolderShareRecord",
  "docferry.deleteShareRecord",
  "docferry.openDashboard",
  "docferry.openUrl",
  "docferry.refresh",
  "docferry.saveLink",
  "docferry.shareCurrentFile",
  "docferry.shareFolder",
  "docferry.showMembership",
  "docferry.signIn",
  "docferry.signOut",
  "docferry.stopFolderShare",
  "docferry.stopShare",
  "docferry.updateFolderShare",
  "docferry.updateShare"
] as const;


export async function run(): Promise<void> {
  const extension = vscode.extensions.getExtension("bondie.docferry");
  assert.ok(extension, "DocFerry extension was not discovered by Extension Host");
  await extension.activate();
  assert.equal(extension.isActive, true);
  assert.equal(extension.packageJSON.version, "0.2.0");
  assert.equal(extension.packageJSON.pricing, "Free");
  assert.equal(extension.packageJSON.preview, true);
  assert.equal(extension.packageJSON.capabilities.untrustedWorkspaces.supported, false);
  assert.equal(extension.packageJSON.capabilities.virtualWorkspaces.supported, false);

  const commands = new Set(await vscode.commands.getCommands(true));
  for (const command of EXPECTED_COMMANDS) {
    assert.ok(commands.has(command), `Extension Host did not register ${command}`);
  }

  await vscode.commands.executeCommand("docferry.refresh");
}
