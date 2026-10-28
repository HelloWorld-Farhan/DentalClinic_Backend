/**
 * ==============================================================================
 * Smile Clinic — Google Apps Script Email Gateway v1.2
 * ==============================================================================
 * 
 * INSTRUCTIONS FOR DEPLOYMENT:
 * 1. Open https://script.google.com in your browser (signed in as support.smileclinic@gmail.com).
 * 2. Click "New Project" and rename it to "Smile Clinic Mail Gateway".
 * 3. Replace all existing code in Code.gs with this exact file content.
 * 4. Click "Deploy" (top right) -> "Manage deployments" -> "Edit" (or "New deployment").
 * 5. Select type: "Web app".
 * 6. Set Description: "Smile Clinic Email API v1.2 (With Attachment & R2 Support)".
 * 7. Set "Execute as": "Me (support.smileclinic@gmail.com)".
 * 8. Set "Who has access": "Anyone"  <-- CRITICAL for backend to send requests without login.
 * 9. Click "Deploy", approve permissions if prompted.
 * ==============================================================================
 */

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return ContentService.createTextOutput(JSON.stringify({
        status: "error",
        message: "No post data received."
      })).setMimeType(ContentService.MimeType.JSON);
    }

    var data = JSON.parse(e.postData.contents);
    var recipient = data.to;
    var subject = data.subject || "Smile Clinic Notification";
    var htmlBody = data.html || "<p>Smile Clinic Clinical Notification</p>";
    var plainText = data.text || "Please view this clinical message in an HTML-enabled email client.";

    if (!recipient) {
      return ContentService.createTextOutput(JSON.stringify({
        status: "error",
        message: "Missing 'to' recipient email address."
      })).setMimeType(ContentService.MimeType.JSON);
    }

    var mailOptions = {
      name: "Smile Clinic",
      htmlBody: htmlBody
    };

    // Support optional direct base64 file attachment (PDF / Word / CSV)
    if (data.attachment_base64 && data.attachment_name) {
      try {
        var decodedBytes = Utilities.base64Decode(data.attachment_base64);
        var mimeType = data.attachment_type || "application/pdf";
        var attachmentBlob = Utilities.newBlob(decodedBytes, mimeType, data.attachment_name);
        mailOptions.attachments = [attachmentBlob];
      } catch (attachErr) {
        Logger.log("Attachment processing error: " + attachErr.toString());
      }
    }

    // Send email using official Google infrastructure from support.smileclinic@gmail.com
    GmailApp.sendEmail(recipient, subject, plainText, mailOptions);

    return ContentService.createTextOutput(JSON.stringify({
      status: "success",
      message: "Email dispatched successfully to " + recipient,
      hasAttachment: !!mailOptions.attachments
    })).setMimeType(ContentService.MimeType.JSON);

  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({
      status: "error",
      message: error.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  return ContentService.createTextOutput(JSON.stringify({
    status: "active",
    service: "Smile Clinic Google Apps Script Mail Gateway v1.2",
    sender: "support.smileclinic@gmail.com",
    features: ["HTML Templates", "R2 Download Links", "PDF Attachments"]
  })).setMimeType(ContentService.MimeType.JSON);
}
