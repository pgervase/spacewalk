<%@ taglib uri="http://rhn.redhat.com/rhn" prefix="rhn" %>
<%@ taglib uri="http://struts.apache.org/tags-bean" prefix="bean" %>

<html>
<body>

<h1>
  <rhn:icon type="system-warn" title="<bean:message key='error.common.errorAlt' />" />
  <bean:message key="unknown.kickstart" />:
</h1>

<p><bean:message key="unknown.kickstart.message" /></p>

</body>
</html>
