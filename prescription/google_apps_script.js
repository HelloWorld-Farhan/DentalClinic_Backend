/**
 * ==============================================================================
 * Smile Clinic — Google Apps Script Email Gateway v1.3 (Production Hardened)
 * ==============================================================================
 * 
 * INSTRUCTIONS FOR DEPLOYMENT:
 * 1. Open https://script.google.com in your browser (signed in as support.smileclinic@gmail.com).
 * 2. Open project "Smile Clinic Mail Gateway".
 * 3. Replace all existing code in Code.gs with this exact file content.
 * 4. Click "Deploy" (top right) -> "Manage deployments" -> Edit (pencil icon) -> Version: "New version".
 * 5. Set "Execute as": "Me (support.smileclinic@gmail.com)".
 * 6. Set "Who has access": "Anyone".
 * 7. Click "Deploy" and authorize permissions if prompted.
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
    var recipient = data.to || data.to_email || data.recipient || data.email;
    var cc = data.cc || data.cc_email || data.clinician_email;
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

    if (cc && typeof cc === "string" && cc.indexOf("@") !== -1 && cc !== recipient) {
      mailOptions.cc = cc;
    }

    if (data.replyTo) {
      mailOptions.replyTo = data.replyTo;
    }

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

    // Dual-engine dispatch: Try MailApp then GmailApp fallback
    var delivered = false;
    var deliveryMethod = "";
    var lastError = "";

    try {
      MailApp.sendEmail(recipient, subject, plainText, mailOptions);
      delivered = true;
      deliveryMethod = "MailApp";
    } catch (mailErr) {
      lastError = mailErr.toString();
      try {
        GmailApp.sendEmail(recipient, subject, plainText, mailOptions);
        delivered = true;
        deliveryMethod = "GmailApp";
      } catch (gmailErr) {
        lastError += " | " + gmailErr.toString();
      }
    }

    if (delivered) {
      return ContentService.createTextOutput(JSON.stringify({
        status: "success",
        message: "Email dispatched successfully to " + recipient + (mailOptions.cc ? " (CC: " + mailOptions.cc + ")" : ""),
        method: deliveryMethod,
        recipient: recipient,
        cc: mailOptions.cc || null,
        hasAttachment: !!mailOptions.attachments
      })).setMimeType(ContentService.MimeType.JSON);
    } else {
      return ContentService.createTextOutput(JSON.stringify({
        status: "error",
        message: "Both MailApp and GmailApp delivery failed: " + lastError
      })).setMimeType(ContentService.MimeType.JSON);
    }

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
    service: "Smile Clinic Google Apps Script Mail Gateway v1.3",
    sender: "support.smileclinic@gmail.com",
    features: ["HTML Templates", "CC to Clinician", "Dual Dispatch (MailApp+GmailApp)", "PDF Attachments"]
  })).setMimeType(ContentService.MimeType.JSON);
}

function doOptions(e) {
  return ContentService.createTextOutput("")
    .setMimeType(ContentService.MimeType.TEXT);
}
